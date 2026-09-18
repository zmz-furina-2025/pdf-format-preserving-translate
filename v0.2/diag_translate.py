import importlib.util, sys
spec = importlib.util.spec_from_file_location("e", "demo_v0.2.1.py")
m = importlib.util.module_from_spec(spec)
sys.modules["e"] = m
spec.loader.exec_module(m)
t = m.TencentTranslator("en", "zh")
result = t.translate_batch([
    "X: the number of Heads.",
    "Y: the number of Tails.",
])
for r in result:
    print(repr(r))
