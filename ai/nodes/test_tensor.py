import torch
from transformers import AutoTokenizer, AutoModel

tokenizer = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1")
model = AutoModel.from_pretrained("nomic-ai/nomic-embed-text-v1")

def embed(text):
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs)
    return output.last_hidden_state.mean(dim=1)[0]

v1 = embed("Koliko NO2 je bilo včeraj?")
v2 = embed("Kakšna je koncentracija NO2?")
v3 = embed("Živjo, kako si?")

cos_12 = torch.nn.functional.cosine_similarity(v1, v2, dim=0)
cos_13 = torch.nn.functional.cosine_similarity(v1, v3, dim=0)

print(f"NO2 vprašanje vs NO2 vprašanje: {cos_12:.4f}")
print(f"NO2 vprašanje vs pozdrav: {cos_13:.4f}")
