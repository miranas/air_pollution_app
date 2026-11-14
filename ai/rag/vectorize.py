import os
import httpx
import pdfplumber
from docx import Document
from bs4 import BeautifulSoup
from ai.db import get_rag_connection
from ai import config
from refinedoc.refined_document import RefinedDocument
from konan import RecursiveChunker
import hashlib
import logging
import re
import unicodedata

logging.basicConfig(level=logging.ERROR)
logging.getLogger("konan").setLevel(logging.ERROR)

SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf", ".docx", ".html", ".htm")


def _normalize_pdf_text(text: str) -> str:
    """Popravi PDF ligature, manjkajoče presledke in združi besede."""
    # 1. Normaliziraj Unicode (kombinirani znaki → sestavljeni)
    text = unicodedata.normalize("NFC", text)

    text = re.sub(r'(\w)<sup>ˇ</sup>', r'\1ˇ', text)  # odstrani <sup> in </sup>, ohrani ˇ
    text = re.sub(r'(\w)<sup>([ˇ´`])</sup>', r'\1\2', text)  # tudi drugi caron znaki

    # 2. Popravi ligature: cˇ → č, sˇ → š, zˇ → ž
    text = text.replace("cˇ", "č").replace("Cˇ", "Č")
    text = text.replace("sˇ", "š").replace("Sˇ", "Š")
    text = text.replace("zˇ", "ž").replace("Zˇ", "Ž")


    # 4. Normaliziraj presledke
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def read_file(path: str) -> str:

    """Preberi datoteko glede na končnico in vrni čisto besedilo."""
    if path.endswith(".txt") or path.endswith(".md"):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    elif path.endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            document = [
                page.extract_text().split("\n")
                for page in pdf.pages
                if page.extract_text()
            ]


        if not document:
            raise ValueError(f"PDF nima besedila: {path}")

        rd = RefinedDocument(content=document)
        full_text = "\n".join(
            " ".join(page_lines) if isinstance(page_lines, list) else str(page_lines)
            for page_lines in rd.body
        )
        full_text = _normalize_pdf_text(full_text)
        return full_text

    elif path.endswith(".docx"):
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    elif path.endswith(".html") or path.endswith(".htm"):
        with open(path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
            return soup.get_text(separator="\n")

    else:
        raise ValueError(f"Nepodprt format: {path}")


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Razdeli besedilo na kose s konan RecursiveChunker."""
    if not text or not text.strip():
        return []

    chunker = RecursiveChunker(chunk_size=max_chars, chunk_overlap=overlap)
    chunks = chunker.chunk(text)

    return [c.text for c in chunks if c.text and c.text.strip()]


def _file_hash(path: str) -> str:
    """Izračunaj SHA-256 hash datoteke."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()



def vectorize_file(path: str) -> int:
    """Vektorizira eno datoteko."""
    source = os.path.basename(path)
    nov_hash = _file_hash(path)

    with get_rag_connection() as conn:
        cur = conn.cursor()

        # 1. Preveri status IN hash
        cur.execute(
            "SELECT status, content_hash FROM rag_sources_status WHERE source = %s;",
            (source,)
        )
        row = cur.fetchone()

        if row:
            status, stari_hash = row
            if status == "done" and stari_hash == nov_hash:
                print(f"Skipping {source} (nespremenjeno)")
                return 0
            if status == "done" and stari_hash != nov_hash:
                print(f"🔄 {source}: datoteka se je spremenila, ponovno vektorižiram")
                cur.execute("DELETE FROM documents WHERE source = %s;", (source,))
                conn.commit()
            if status == "processing":
                print(f"⚠️  {source}: prejšnji poskus je ostal v 'processing', ponavljam")
            if status == "failed":
                print(f"⚠️  {source}: prejšnji poskus je failal, ponavljam")

        # 2. Označi "processing" + shrani hash
        cur.execute("""
                    INSERT INTO rag_sources_status (source, status, content_hash)
                    VALUES (%s, 'processing', %s)
                    ON CONFLICT (source) DO UPDATE
                        SET status = 'processing',
                            content_hash = EXCLUDED.content_hash;
                    """, (source, nov_hash))

        cur.execute("""
                    UPDATE rag_sources_status
                    SET last_error = NULL
                    WHERE source = %s;
                    """, (source,))

        conn.commit()

        try:
            vsebina = read_file(path)
            fragmenti = chunk_text(vsebina, max_chars=1500, overlap=200)

            if not fragmenti:
                raise ValueError("Ni fragmentov – prazen dokument?")

            for fragment in fragmenti:
                response = httpx.post(
                    f"{config.OLLAMA_URL}/api/embeddings",
                    json={"model": config.EMBEDDING_MODEL, "prompt": fragment},
                    timeout=30,
                )
                response.raise_for_status()
                vektor = response.json()["embedding"]

                cur.execute(
                    """
                    INSERT INTO documents (content, embedding, source) VALUES (%s, %s, %s)
                    ON CONFLICT (source, content) DO NOTHING
                    """,
                    (fragment, vektor, source)
                )

            conn.commit()

            cur.execute(
                "SELECT COUNT(*) FROM documents WHERE source = %s;",
                (source,)
            )
            dejansko = cur.fetchone()[0]
            if dejansko != len(fragmenti):
                raise RuntimeError(
                    f"Neskladje: {len(fragmenti)} fragmentov, {dejansko} vrstic v bazi"
                )

            cur.execute("""
                        UPDATE rag_sources_status
                        SET status       = 'done',
                            chunks_count = %s,
                            processed_at = NOW()
                        WHERE source = %s;
                        """, (len(fragmenti), source))

            cur.execute("""
                        UPDATE rag_sources_status
                        SET last_error = NULL
                        WHERE source = %s;
                        """, (source,))

            conn.commit()

            print(f"✅ {source}: {len(fragmenti)} fragmentov")
            return len(fragmenti)

        except Exception as e:
            conn.rollback()

            cur.execute("""
                        UPDATE rag_sources_status
                        SET status       = 'failed',
                            chunks_count = 0
                        WHERE source = %s;
                        """, (source,))

            cur.execute("""
                        UPDATE rag_sources_status
                        SET last_error = %s
                        WHERE source = %s;
                        """, (str(e), source))

            conn.commit()
            print(f"❌ {source}: {e}")
            raise


def vectorize_all(folder: str = "rag_sources") -> dict:
    results = {}
    for filename in os.listdir(folder):
        if not filename.endswith(SUPPORTED_EXTENSIONS):
            continue
        path = os.path.join(folder, filename)
        try:
            results[filename] = vectorize_file(path)
        except Exception as e:
            print(f"⚠️  {filename} failal: {e}")
            results[filename] = None
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
        vectorize_file(path)
    else:
        vectorize_all()