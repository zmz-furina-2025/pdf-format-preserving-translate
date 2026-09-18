"""
make_sample.py —— 测试 PDF（v3：含粗体片段）。
左栏正文里 "layout-preserving translation" 用粗体，验证占位符机制。
"""
import fitz

doc = fitz.open()
page = doc.new_page()

# 标题
page.insert_text((72, 80), "PDF Translation Demo", fontsize=24, fontname="hebo")

# ---- 左栏：普通文字 + 粗体片段 ----
# 普通部分用 helv，粗体部分用 hebo
y = 120
page.insert_text((72, y), "This paper presents a new,", fontsize=11, fontname="helv"); y += 16
# 粗体一行
page.insert_text((72, y), "layout-preserving translation", fontsize=11, fontname="hebo"); y += 16
page.insert_text((72, y), "approach. It keeps multi-column", fontsize=11, fontname="helv"); y += 16
page.insert_text((72, y), "text, figures and footnotes", fontsize=11, fontname="helv"); y += 16
page.insert_text((72, y), "in original positions.", fontsize=11, fontname="helv"); y += 16

# ---- 右栏 ----
page.insert_text((295, 120), "Right Column", fontsize=14, fontname="hebo")
right_lines = [
    "The second column starts here.",
    "After translation, this paragraph",
    "should wrap within the same width.",
]
y = 145
for line in right_lines:
    page.insert_text((295, y), line, fontsize=10, fontname="helv")
    y += 15

# 脚注
page.insert_text(
    (72, 330),
    "Note: this footnote uses 8pt gray text.",
    fontsize=8, fontname="heit", color=(0.4, 0.4, 0.4),
)

out = "sample_v3.pdf"
doc.save(out)
doc.close()
print(f"[OK] 已生成 {out}")
