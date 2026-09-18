import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
seen_colors = {}
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        for sp in line["spans"]:
            t = sp["text"].strip()
            if not t: continue
            c = sp["color"]
            seen_colors[c] = seen_colors.get(c, 0) + 1
            if c not in (0, 0xFFFFFF):
                r = (c >> 16) & 255; g = (c >> 8) & 255; bl = c & 255
                bb = tuple(round(v,1) for v in sp["bbox"])
                print(f"color=0x{c:06x} rgb=({r},{g},{bl}) bbox={bb} text={t[:30]!r}")
doc.close()
