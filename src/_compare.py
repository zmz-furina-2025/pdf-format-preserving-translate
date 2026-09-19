import fitz

doc1 = fitz.open(r"D:\大学笔记\4.大二上\CS101\2023课件\Lecture_4-Algorithm_Analysis-Lecture.pdf")
doc2 = fitz.open(r"C:\Users\Lenovo\Downloads\tmpvwzq0mgd.pdf")

print("=== 原文第 3 页 ===")
page1 = doc1[2]
blocks1 = page1.get_text("dict")["blocks"]
for i, b in enumerate(blocks1):
    if "lines" in b:
        texts = []
        for line in b["lines"]:
            for span in line["spans"]:
                t = span["text"].strip()
                if t:
                    texts.append(t)
        full = " ".join(texts)
        if full:
            print(f"  [{i}] bbox=({b['bbox'][0]:.0f},{b['bbox'][1]:.0f},{b['bbox'][2]:.0f},{b['bbox'][3]:.0f}) text={full[:80]}")

print("\n=== 译文第 3 页 ===")
page2 = doc2[2]
blocks2 = page2.get_text("dict")["blocks"]
for i, b in enumerate(blocks2):
    if "lines" in b:
        texts = []
        for line in b["lines"]:
            for span in line["spans"]:
                t = span["text"].strip()
                if t:
                    texts.append(t)
        full = " ".join(texts)
        if full:
            print(f"  [{i}] bbox=({b['bbox'][0]:.0f},{b['bbox'][1]:.0f},{b['bbox'][2]:.0f},{b['bbox'][3]:.0f}) text={full[:80]}")

doc1.close()
doc2.close()
