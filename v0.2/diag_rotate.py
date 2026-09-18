"""
诊断横向 PDF 的旋转情况。
用法：python diag_rotate.py 你的横向文件.pdf
"""
import sys, fitz

if len(sys.argv) < 2:
    print("用法: python diag_rotate.py <pdf路径>")
    sys.exit(1)

doc = fitz.open(sys.argv[1])
for i, page in enumerate(doc):
    print(f"--- 第 {i+1} 页 ---")
    print(f"  page.rect     = {page.rect}")
    print(f"  page.rotation = {page.rotation}")
    print(f"  page.derotation_matrix = {page.derotation_matrix}")
    d = page.get_text("dict")
    n = 0
    for b in d["blocks"]:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for sp in line["spans"]:
                if not sp["text"].strip(): continue
                print(f"  span bbox={tuple(round(v,1) for v in sp['bbox'])} "
                      f"origin={tuple(round(v,1) for v in sp['origin'])} "
                      f"dir={line.get('dir')} text={sp['text'][:30]!r}")
                n += 1
                if n >= 5: break
            if n >= 5: break
        if n >= 5: break
doc.close()
