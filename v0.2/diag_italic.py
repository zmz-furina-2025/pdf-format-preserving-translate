import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]  # 第6页有 Σ
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        for sp in line["spans"]:
            t = sp["text"].strip()
            if not t: continue
            flags = sp["flags"]
            italic = bool(flags & 1)
            bold = bool(flags & 16)
            font = sp["font"]
            print(f"flags={flags:4d} italic={italic!s:5s} bold={bold!s:5s} font={font:30s} size={sp['size']:.1f} text={t[:40]!r}")
doc.close()
