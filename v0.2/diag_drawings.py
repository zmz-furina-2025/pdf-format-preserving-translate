import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]
drawings = page.get_drawings()
for d in drawings[:15]:
    r = d["rect"]
    print(f"  rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f}) color={d.get('color')} fill={d.get('fill')} type={d.get('type')}")
print("---images---")
for img in page.get_images(full=True):
    print(f"  xref={img[0]} size={img[2]}x{img[3]}")
# 看 image 位置
for item in page.get_image_info():
    r = item["bbox"]
    print(f"  image bbox=({r[0]:.1f},{r[1]:.1f},{r[2]:.1f},{r[3]:.1f})")
doc.close()
