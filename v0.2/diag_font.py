import fitz
doc = fitz.open("L3-2024Fall-handwriting - 副本.pdf")
for pno in range(len(doc)):
    page = doc[pno]
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for sp in line["spans"]:
                t = sp["text"].strip()
                if t and ("head" in t.lower() or "tail" in t.lower()):
                    print(f"p{pno} font={sp['font']} size={sp['size']:.1f} text={sp['text']!r}")
doc.close()
