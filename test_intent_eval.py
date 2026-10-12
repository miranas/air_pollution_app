from transformers import pipeline
from sklearn.metrics import accuracy_score, f1_score

print("Nalagam model ...")
router = pipeline("text-classification", model="tripathyShaswata/AgentIntentRouter")
print("Model naložen.\n")

testni_podatki = [
    ("Koliko NO2 je bilo včeraj?", "sql_query"),
    ("Kaj piše v pravilniku?", "rag_search"),
    ("Živjo!", "general_chat"),
]

napovedi = []
resnice = []
for vpr, pravilna in testni_podatki:
    rezultat = router(vpr)[0]
    print(f"{vpr!r:50} -> {rezultat['label']:20} (score={rezultat['score']:.2f})")
    napovedi.append(rezultat['label'])
    resnice.append(pravilna)

print(f"\nTočnost: {accuracy_score(resnice, napovedi):.2f}")
print(f"F1 (weighted): {f1_score(resnice, napovedi, average='weighted'):.2f}")
