"""
make_sample_bg.py —— 测试"非纯色背景"场景：
  1) 深蓝色块上白字（矢量背景）
  2) 渐变图片上黑字（光栅背景）
  3) 正常白底文字（对照）
"""
import os
from PIL import Image, ImageDraw
import fitz

# 1) 生成一张渐变测试图
img_path = "test_bg.png"
img = Image.new("RGB", (260, 120), (200, 200, 200))
draw = ImageDraw.Draw(img)
for x in range(260):
    c = int(180 + (200 - 180) * x / 260)
    draw.line([(x, 0), (x, 120)], fill=(c, 120, 80))
img.save(img_path)

doc = fitz.open()
page = doc.new_page()

# 2) 深蓝色块 + 白字（矢量背景）
bg_rect = fitz.Rect(72, 80, 320, 140)
page.draw_rect(bg_rect, fill=(0.15, 0.25, 0.55), color=None)
page.insert_text(
    (82, 108), "White text on dark blue block.",
    fontsize=12, fontname="helv", color=(1, 1, 1),
)
page.insert_text(
    (82, 128), "This should keep the blue background.",
    fontsize=10, fontname="helv", color=(1, 1, 1),
)

# 3) 渐变图片 + 黑字（光栅背景）
img_rect = fitz.Rect(72, 170, 332, 290)
page.insert_image(img_rect, filename=img_path)
page.insert_text(
    (82, 195), "Black text over a gradient image.",
    fontsize=11, fontname="helv", color=(0, 0, 0),
)
page.insert_text(
    (82, 215), "The image must not be erased.",
    fontsize=10, fontname="helv", color=(0, 0, 0),
)

# 4) 正常白底对照
page.insert_text((72, 330), "Normal white background text.",
                 fontsize=11, fontname="helv", color=(0, 0, 0))

out = "sample_bg.pdf"
doc.save(out)
doc.close()
print(f"[OK] 已生成 {out}")
