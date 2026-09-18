with open("demo_v0.5.1.1.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """    def _join_block_text(blk: Block) -> str:
        parts = []
        for line in blk.lines:
            line_text = ""
            cur_math = ""
            def flush_math():
                nonlocal cur_math
                if cur_math:
                    if len(cur_math.strip()) >= 2:
                        blk.math_symbols.append(cur_math.strip())
                    cur_math = ""
            for s in line:
                line_text += s.text  # span text 自带空格
                if s.is_math:
                    cur_math += s.text
                else:
                    flush_math()"""

new = """    def _join_block_text(blk: Block) -> str:
        # CMSY 字体字符 → Unicode 符号映射
        _cmsy_map = {'1': '\\u03a3', '2': '\\u03a0', '4': '\\u222b', '5': '\\u222e', '6': '\\u22c3', '7': '\\u22c2'}
        parts = []
        for line in blk.lines:
            line_text = ""
            cur_math = ""
            def flush_math():
                nonlocal cur_math
                if cur_math:
                    if len(cur_math.strip()) >= 2:
                        blk.math_symbols.append(cur_math.strip())
                    cur_math = ""
            for s in line:
                # CMSY 字体的特殊字符映射成 Unicode
                text = s.text
                if s.font_name.startswith('CMSY'):
                    text = ''.join(_cmsy_map.get(c, c) for c in text)
                line_text += text  # span text 自带空格
                if s.is_math:
                    cur_math += text
                else:
                    flush_math()"""

if old in content:
    content = content.replace(old, new)
    with open("demo_v0.5.1.1.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("replaced")
else:
    print("not found")
