import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
pix = page.get_pixmap(dpi=100)
pix.save("orig_p6.png")
for b in page.get_text("dict")["blocks"]:
    bt = b["type"]
    bb = tuple(round(v,1) for v in b["bbox"])
    print(f"type={bt} bbox={bb}")
# 看 rawdict 里有没有别的
print("--- blocks with type 1 (image) ---")
for b in page.get_text("dict")["blocks"]:
    if b["type"] == 1:
        print(f"  bbox={tuple(round(v,1) for v in b['bbox'])}")
doc.close()
