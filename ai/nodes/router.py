import .env

LABEL_MAP = {
    "data_analysis": "SQL",
    "math_calculation": "SQL",
    "web_search": "RAG",
    "file_operation": "RAG",
    "general_chat": "SPLOŠNO",
    "creative_writing": "SPLOŠNO",
    "code_generation": "SPLOŠNO",
    "api_call": "SPLOŠNO",
}


============================================================
# 4. GLAVNA FUNKCIJA
# ============================================================

def route(question: str) -> str:
    """
    Glavna funkcija – vrne 'SQL', 'RAG' ali 'SPLOŠNO'.
    """

    # 2. Klasificiraj
    label, score = classify(prevod)

    # 3. Mapiraj
    kategorija = LABEL_MAP.get(label, "SPLOŠNO")

    return kategorija

from ai.nodes.router import route, translate_sl_to_en, classify

vprasanja = [
    "Koliko NO2 je bilo včeraj v Novi Gorici?",
    "Povprečje PM10 v Ljubljani za junij.",
    "Kdaj so večerni viški NOx?",
    "Kaj piše v pravilniku o mejnih vrednostih?",
    "Mejna vrednost za ozon?",
    "Kaj določa uredba o kakovosti zraka?",
    "Živjo, kako si?",
    "Hvala, nasvidenje!",
]

print(f"{'Vprašanje':<50} {'Prevod':<45} {'Label':<20} {'Kat.'}")
print("=" * 130)

for vpr in vprasanja:
    prevod = translate_sl_to_en(vpr)
    label, score = classify(prevod)
    kategorija = route(vpr)
    print(f"{vpr:<50} {prevod[:43]:<45} {label:<20} {kategorija}")







