import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
annots = list(page.annots())
print(f"annots count: {len(annots)}")
for a in annots[:10]:
    r = a.rect
    print(f"  type={a.type[1]} rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f})")
doc.close()
