#from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from transformers import MarianMTModel, MarianTokenizer
import torch
import time


"""
model_name = "facebook/nllb-200-distilled-600M"

print("Loading tokenizer in model ...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)


device  = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)
print(f"I use {device}")



tokenizer.src_lang = "slv_Latn"

def translate_sl_to_en(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        translated = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids("eng_Latn"),
            max_length=128
            )
    return tokenizer.decode(translated[0], skip_special_tokens=True)
"""

model_name = "Helsinki-NLP/opus-mt-sla-en"
tokenizer = MarianTokenizer.from_pretrained(model_name)
model = MarianMTModel.from_pretrained(model_name)

def translate(text):
    text_with_token = ">>slv<< " + text
    inputs = tokenizer(text_with_token, return_tensors="pt", padding=True)
    translated = model.generate(**inputs, max_length=128)
    return tokenizer.decode(translated[0], skip_special_tokens=True)

questions = [
    "Kje je Novo mesto?",
    "Kaj piše v pravilniku o mejnih vrednostih?",
    "Živjo, kako si?",
]

model_name = "Helsinki-NLP/opus-mt-sla-en"
tokenizer = MarianTokenizer.from_pretrained(model_name)
model = MarianMTModel.from_pretrained(model_name)


for vpr in questions:
    start = time.time()
    prevod = translate(vpr)
    cas = time.time() - start
    print(f"SL:  {vpr}")
    print(f"EN:  {prevod}")
    print(f"Čas: {cas:.2f}s\n")

"""
for question in questions:
    start=time.time()
    translate = translate_sl_to_en(question)
    timing = time.time() - start
    print(f"SL: question: {question}")
    print(f" ENG: translate: {translate}")
    print(f"Time: {timing:.2f}s\n")


    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch
from transformers import ...: Uvozi dva razreda iz knjižnice Hugging Face transformers. AutoTokenizer poskrbi, da se besedilo pravilno razdeli na manjše enote (tokene), ki jih model razume. AutoModelForSeq2SeqLM naloži model, ki je namenjen pretvorbi enega zaporedja v drugo (npr. prevajanju).

import torch: Uvozi PyTorch, knjižnico za globoko učenje. Modeli v transformers tečejo na PyTorchu. Če ga ne bi uvozili, ne bi mogli preveriti, ali je na voljo GPU, niti ne bi mogli poganjati modela.

python
model_name = "facebook/nllb-200-distilled-600M"
model_name: To je ime modela na Hugging Face. facebook/nllb-200-distilled-600M pomeni, da gre za Meta-in model NLLB-200 (No Language Left Behind), ki je bil destiliran (pomanjšan) na 600 milijonov parametrov. Ta model zna prevajati med več kot 200 jeziki, vključno s slovenščino.

python
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
AutoTokenizer.from_pretrained(model_name): Naloži tokenizer, ki ustreza temu modelu. Tokenizer pretvori besedilo (npr. "Koliko NO2 je bilo včeraj?") v zaporedje številk (tokenov), ki jih model lahko obdela.

AutoModelForSeq2SeqLM.from_pretrained(model_name): Naloži same uteži modela. Seq2SeqLM pomeni, da gre za model, ki bere eno zaporedje (vhodno vprašanje) in generira drugo (prevedeno vprašanje). from_pretrained poskrbi, da se uteži prenesejo iz Hugging Face in naložijo v pomnilnik.

python
device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)
print(f"Uporabljam: {device}")
device = "cuda" if torch.cuda.is_available() else "cpu": Preveri, ali je na voljo NVIDIA GPU (CUDA). Če je, bo model tekel na GPU (hitreje). Če ni, bo tekel na CPU.

model = model.to(device): Premakne model na izbrano napravo. Če je device "cuda", se model naloži v VRAM. Če je "cpu", ostane v sistemskem RAM-u.

print(...): Samo izpiše, katero napravo uporabljaš. To je uporabno za debugging.

python
def translate_sl_to_en(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True).to(device)
    translated = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids("eng_Latn"),
        max_length=128
    )
    return tokenizer.decode(translated[0], skip_special_tokens=True)
def translate_sl_to_en(text):: Definira funkcijo, ki prejme slovensko besedilo in vrne angleški prevod.

inputs = tokenizer(text, return_tensors="pt", padding=True).to(device):

tokenizer(text, ...): Pretvori besedilo v tokene.

return_tensors="pt": Vrne PyTorch tensorje (ne NumPy arrayev).

padding=True: Če je besedilo krajše od maksimalne dolžine, doda "padding" (prazne tokene), da so vsi vhodi enako dolgi.

.to(device): Premakne tensorje na isto napravo, kjer je model (GPU ali CPU).

model.generate(...): To je glavni klic, ki požene model. Model generira prevod.

**inputs: Razpakira slovar inputs (ki vsebuje input_ids in attention_mask) kot argumente.

forced_bos_token_id=tokenizer.convert_tokens_to_ids("eng_Latn"): To je ključno za NLLB. Model mora vedeti, v kateri jezik naj prevaja. eng_Latn je koda za angleščino (Latinica). Ta parameter prisili model, da generira angleške tokene.

max_length=128: Prepreči, da bi prevod bil predolg (varnostna meja).

return tokenizer.decode(translated[0], skip_special_tokens=True):

translated[0]: Model vrne tensorje za vsak vhod. Vzamemo prvega (ker imamo eno vprašanje).

tokenizer.decode(...): Pretvori tokene nazaj v berljivo besedilo.

skip_special_tokens=True: Odstrani posebne tokene (npr. [CLS], [SEP]), ki jih model uporablja interno, a jih v končnem prevodu ne želimo.

python
vprasanja = [
    "Koliko NO2 je bilo včeraj v Novi Gorici?",
    "Kaj piše v pravilniku o mejnih vrednostih?",
    "Živjo, kako si?",
]
To je seznam testnih vprašanj. Namenoma so različna: eno je SQL (meritve), eno RAG (dokumenti), eno SPLOŠNO (klepet).

python
for vpr in vprasanja:
    prevod = translate_sl_to_en(vpr)
    print(f"SL: {vpr}")
    print(f"EN: {prevod}\n")
for vpr in vprasanja:: Gremo skozi vsako vprašanje.

prevod = translate_sl_to_en(vpr): Pokličemo funkcijo, ki prevede.

print(...): Izpišemo original in prevod.

"""





