import importlib.util, sys
spec = importlib.util.spec_from_file_location("e", "demo_v0.2.1.py")
m = importlib.util.module_from_spec(spec)
sys.modules["e"] = m
spec.loader.exec_module(m)
import fitz
doc = fitz.open("L3-2024Fall-handwriting - 副本.pdf")
page = doc[5]
tr = m.VectorPdfTranslator(lambda x: x, "zh")
raw = tr._collect_blocks(page)
blocks = tr._merge_blocks(raw)
for i, b in enumerate(blocks):
    t = m.VectorPdfTranslator._join_block_text(b)
    if t.strip():
        w = b.bbox[2] - b.bbox[0]
        print(f"block {i}: width={w:.1f} text={t[:60]!r}")
doc.close()
