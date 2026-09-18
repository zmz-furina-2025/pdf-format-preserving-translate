with open("demo_v0.5.1.1.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到 _join_block_text 的位置
start = None
for i, line in enumerate(lines):
    if "def _join_block_text(blk: Block) -> str:" in line:
        start = i
        break

print("start line:", start+1)

# 替换 start 行的内容
new_code = '''    def _join_block_text(blk: Block) -> str:
        # CMSY 字体字符 → Unicode 符号映射
        cmsy_map = {
            '1': '\\u03a3',  # 求和
            '2': '\\u03a0',  # 乘积
            '4': '\\u222b',  # 积分
            '5': '\\u222e',  # 环路积分
            '6': '\\u22c3',  # 并集
            '7': '\\u22c2',  # 交集
            '8': '\\u2295',  # 直和
            '9': '\\u2297',  # 直积
            '0': '\\u2299',  # 直积
        }
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
                    mapped = ''.join(cmsy_map.get(c, c) for c in text)
                    text = mapped
                line_text += text  # span text 自带空格
                if s.is_math:
                    cur_math += text
                else:
                    flush_math()
'''

# 找到 _join_block_text 函数结束的位置（下一个 def 或 @staticmethod）
end = start + 1
while end < len(lines):
    line = lines[end]
    if line.strip().startswith("def ") or line.strip().startswith("@staticmethod"):
        break
    end += 1

print("end line:", end+1)

# 替换
lines[start:end] = [new_code]

with open("demo_v0.5.1.1.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("replaced")
