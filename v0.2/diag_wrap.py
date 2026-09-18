import importlib.util, sys
spec = importlib.util.spec_from_file_location("e", "demo_v0.2.1.py")
m = importlib.util.module_from_spec(spec)
sys.modules["e"] = m
spec.loader.exec_module(m)

tr = m.VectorPdfTranslator(lambda x: x, "zh")
text = "一个随机变量X被称为离散的，如果有一个有限的值列表a1，a2，…，aj，对于某些j，P(X=aj)=1。如果X是离散的r.v.，那么使P(X=x)>0的有限或有限值x集称为X的支持。"
tokens = [(text, 0)]
wrapped = tr._wrap_rich(tokens, 660.0, 23.8)
print(f"num lines: {len(wrapped)}")
for i, ln in enumerate(wrapped):
    w = sum(tr._char_width(ch, fl, 23.8) for ch, fl in ln)
    print(f"  line {i}: width={w:.1f}pt text={''.join(c for c,_ in ln)[:40]!r}")
