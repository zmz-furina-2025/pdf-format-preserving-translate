with open("demo_v0.5.7.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = """            # 收集所有 math span
            all_math_spans = []
            for blk in blocks:
                for line in blk.lines:
                    for s in line:
                        if s.is_math and s.text.strip():
                            all_math_spans.append(s)
            # 找 CMSY/CMEX 字体的 span（求和符号、积分等）
            complex_spans = [s for s in all_math_spans if s.font_name.startswith("CMSY") or s.font_name.startswith("CMEX")]
            # 对每个复杂符号，找到它的下标 span
            math_spans = []
            used = set()
            for s in complex_spans:
                sub_spans = []
                for other in all_math_spans:
                    if other is s or id(other) in used:
                        continue
                    # x 范围重叠
                    if other.bbox[0] < s.bbox[2] + 10 and other.bbox[2] > s.bbox[0] - 10:
                        # y 中心在 s 中心下方
                        s_cy = (s.bbox[1] + s.bbox[3]) / 2
                        other_cy = (other.bbox[1] + other.bbox[3]) / 2
                        if other_cy > s_cy:
                            sub_spans.append(other)
                # 合并 bbox
                all_spans = [s] + sub_spans
                x0 = min(t.bbox[0] for t in all_spans)
                y0 = min(t.bbox[1] for t in all_spans)
                x1 = max(t.bbox[2] for t in all_spans)
                y1 = max(t.bbox[3] for t in all_spans)
                math_spans.append((fitz.Rect(x0, y0, x1, y1), all_spans))
                for t in all_spans:
                    used.add(id(t))
            # 对每个公式区域，用 qwen2.5vl 识别
            for i, (rect, spans) in enumerate(math_spans):
                latex = self._formula_recognizer(page, rect)
                if latex:
                    ph = f"[[MATH{i}]]"
                    math_map[ph] = latex
                    for s in spans:
                        s.text = ph
""".split("\n")

lines[1087:1112] = [line + "\n" for line in new_lines]

with open("demo_v0.5.7.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("replaced")
