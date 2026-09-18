import fitz
doc = fitz.open("L3-2024Fall-handwriting.pdf")
page = doc[5]  # 第6页

# 所有文字 span
text_items = []
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0: continue
    for line in b["lines"]:
        for sp in line["spans"]:
            if sp["text"].strip():
                text_items.append((line["bbox"], sp["bbox"], sp["text"]))

# 所有图片
img_bboxes = []
for item in page.get_image_info():
    r = item["bbox"]
    w, h = r[2]-r[0], r[3]-r[1]
    if 30 < w < 400 and 10 < h < 80:  # 小图才是公式，不是背景块
        img_bboxes.append((r[0], r[1], r[2], r[3]))

print("=== 文字行 ===")
for lb, sb, t in text_items:
    # 找这一行 y 范围内的图片
    imgs_here = [(x0,y0,x1,y1) for x0,y0,x1,y1 in img_bboxes if y0 < lb[3] and y1 > lb[1]]
    flag = f"  <-- 公式图片: {imgs_here}" if imgs_here else ""
    print(f"  line y=({lb[1]:.0f},{lb[3]:.0f}) x=({lb[0]:.0f},{lb[2]:.0f}) text={t[:50]!r}{flag}")

print(f"\n=== 小图片（候选公式）共 {len(img_bboxes)} ===")
for x0,y0,x1,y1 in img_bboxes:
    print(f"  ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})  {x1-x0:.0f}x{y1-y0:.0f}")
doc.close()
