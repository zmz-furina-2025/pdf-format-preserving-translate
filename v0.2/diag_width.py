import importlib.util, sys
spec = importlib.util.spec_from_file_location("e", "demo_v0.2.1.py")
m = importlib.util.module_from_spec(spec)
sys.modules["e"] = m
spec.loader.exec_module(m)

tr = m.VectorPdfTranslator(lambda x: x, "zh")
text = "一个随机变量X被称为离散的，如果有一个有限的值列表"
w_measured = sum(tr._char_width(ch, 0, 23.8) for ch in text)
print(f"measured width: {w_measured:.1f}pt")
print(f"block width: {700 - 50:.1f}pt")
print(f"fits: {w_measured <= 650}")
