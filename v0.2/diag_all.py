import fitz
doc = fitz.open("L3-2024Fall-handwriting - 副本.pdf")
page = doc[7]
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        texts = [(sp["font"], sp["text"]) for sp in line["spans"]]
        print(texts)
doc.close()
