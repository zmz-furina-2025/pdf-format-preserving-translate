import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        sizes = [sp["size"] for sp in line["spans"]]
        main_size = max(sizes)
        main_origin = [sp["origin"][1] for sp in line["spans"] if sp["size"] == main_size][0]
        for sp in line["spans"]:
            t = sp["text"].strip()
            if not t: continue
            if sp["size"] < main_size * 0.7 and t:
                oy = sp["origin"][1]
                kind = "SUP" if oy < main_origin - main_size*0.15 else ("SUB" if oy > main_origin + main_size*0.15 else "?")
                print(f"{kind} size={sp['size']:.1f} main={main_size:.1f} oy={oy:.1f} main_oy={main_origin:.1f} text={t!r}")
doc.close()
