import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        for sp in line["spans"]:
            t = sp["text"].strip()
            if not t: continue
            c = sp["color"]
            r = (c >> 16) & 255; g = (c >> 8) & 255; bl = c & 255
            if r > 150 and g < 100 and bl < 100:  # 红色
                print(f"RED span: color=0x{c:06x} rgb=({r},{g},{bl}) bbox={tuple(round(v,1) for v in sp['bbox'])} text={t!r}")
doc.close()
