import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import importlib.util, fitz
spec = importlib.util.spec_from_file_location("e", os.path.join(os.path.dirname(__file__), "demo_v0.2.1.py"))
e = importlib.util.module_from_spec(spec); sys.modules["e"] = e; spec.loader.exec_module(e)
t = e.VectorPdfTranslator(lambda x: x, "zh")
doc = fitz.open(r"D:\ObsidianDocument\大二上\2023课件\Lecture_4-Algorithm_Analysis-Lecture.pdf")
p = doc[0]
m = p.rotation_matrix
print("rotation:", p.rotation, "matrix:", m)
raw = t._collect_blocks(p, m)
print("raw blocks:", len(raw))
for b in raw:
    print("  bbox=", [round(x,1) for x in b.bbox], "size=", round(b.main_size,1),
          "lines=", len(b.lines), "baselines=", [round(y,1) for y in b.line_baselines],
          "text=", b.lines[0][0].text[:30])
