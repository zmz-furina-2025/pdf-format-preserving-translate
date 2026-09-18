"""
pdf-translate-demo / demo.py  (v3: 段落连续性 + 粗体保留)
=========================================================
相对 v2 的升级：
  1. 跨 block 段落合并：同栏相邻 block（字号/颜色一致、y 间距正常）
     自动拼成一段送翻译，解决"同一段落被 PDF 拆成两个 block"。
  2. 粗体保留：block 内的粗体 span 用 ⟦N⟧ 占位符替换，送翻译后
     解析占位符，粗体部分用雅黑粗体渲染。

流程：
  get_text("dict") → 取 span(含 flags) → 同栏合并 block → 粗体替换成占位符
  → 批量翻译 → 解析占位符成富文本 token → 按宽度换行
  → 逐字符原位渲染（粗体/常规不同字体）
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF


# --------------------------------------------------------------------------- #
# .env
# --------------------------------------------------------------------------- #
def _load_env() -> None:
    # 从当前目录往上找 .env（v0.2/ 子目录跑时能找到根目录的 .env）
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return
        d = os.path.dirname(d)


_load_env()


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Span:
    text: str
    bbox: Tuple[float, float, float, float]
    size: float
    color: int
    flags: int = 0  # PyMuPDF span flags，bit4=bold
    is_math: bool = False  # 公式符号（斜体变量/数学符号），不翻译
    font_name: str = ""  # 原始字体名
    origin_y: float = 0.0  # 基线 y 坐标
    is_sup: bool = False  # 上标
    is_sub: bool = False  # 下标


@dataclass
class Block:
    bbox: Tuple[float, float, float, float]
    lines: List[List[Span]] = field(default_factory=list)
    main_size: float = 11.0
    main_color: int = 0
    line_baselines: List[float] = field(default_factory=list)
    # block 内的小字号粗体术语原文（翻译后在译文中搜索这些词并标粗）
    bold_terms: List[str] = field(default_factory=list)
    # 整个 block 是否全是粗体（标题/栏目标题）
    is_all_bold: bool = False
    # 这一行开头有 bullet 圆点（项目符号），是独立项
    has_bullet: bool = False
    # 这一行开头有数字编号（1. 2. 3.），是独立项
    has_numbering: bool = False
    # 每行原始完整文本（PyMuPDF 已拼好空格）
    line_texts: List[str] = field(default_factory=list)
    # 公式符号原文（{N} 占位符对应的原始 math 文本）
    math_symbols: List[str] = field(default_factory=list)
    # 段落分段：[("text", "英文1"), ("math", "X"), ("text", "英文2"), ...]
    segments: List[Tuple[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 字体
# --------------------------------------------------------------------------- #
BOLD_CN_FONT = r"C:\Windows\Fonts\msyhbd.ttc"
BOLD_CN_FONT_FALLBACK = r"C:\Windows\Fonts\simhei.ttf"
if not os.path.exists(BOLD_CN_FONT):
    BOLD_CN_FONT = BOLD_CN_FONT_FALLBACK


def _is_cjk(ch: str) -> bool:
    """判断字符是否该用中文字体渲染（汉字 + CJK 标点 + 全角符号）。"""
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF:      # CJK 统一汉字
        return True
    if 0x3000 <= o <= 0x303F:      # CJK 标点（、。「」等）
        return True
    if 0xFF00 <= o <= 0xFFEF:      # 全角形式（，。；：（）等）
        return True
    if ch in "…—‘’“”":             # 省略号、破折号、弯引号
        return True
    return False


# --------------------------------------------------------------------------- #
# 翻译器
# --------------------------------------------------------------------------- #
TranslatorFn = Callable[[List[str]], List[str]]


class MockTranslator:
    _POOL = (
        "这是一段用于验证排版还原效果的占位译文，"
        "中文宽度和换行行为将在渲染后人工检查。"
        "当真实翻译接入后，整段会被替换成准确译文。"
    )

    def translate_batch(self, texts: Sequence[str]) -> List[str]:
        out: List[str] = []
        for t in texts:
            s = t.strip()
            if not s or s.isdigit() or (s.startswith("http") and len(s) > 20):
                out.append(t)
                continue
            target = max(10, int(len(s) * 0.55))
            repeated = (self._POOL * (target // len(self._POOL) + 1))[:target]
            out.append(repeated)
        return out


class TencentTranslator:
    HOST = "tmt.tencentcloudapi.com"
    ENDPOINT = "https://tmt.tencentcloudapi.com"
    SERVICE = "tmt"
    VERSION = "2018-03-21"

    def __init__(self, source: str = "en", target: str = "zh"):
        import hashlib
        import hmac
        import time
        self._hmac = hmac
        self._hashlib = hashlib
        self._time = time
        self._secret_id = os.environ.get("TENCENT_SECRET_ID")
        self._secret_key = os.environ.get("TENCENT_SECRET_KEY")
        self._region = os.environ.get("TENCENT_REGION", "ap-shanghai")
        self._source = source
        self._target = target
        if not self._secret_id or not self._secret_key:
            raise RuntimeError("缺少 TENCENT_SECRET_ID / TENCENT_SECRET_KEY")

    def _sign(self, key: bytes, msg: str) -> bytes:
        return self._hmac.new(key, msg.encode("utf-8"), self._hashlib.sha256).digest()

    def _call(self, action: str, payload: dict) -> dict:
        import json
        import requests
        timestamp = int(self._time.time())
        date = self._time.strftime("%Y-%m-%d", self._time.gmtime(timestamp))
        body = json.dumps(payload)
        canonical_headers = (
            f"content-type:application/json; charset=utf-8\n"
            f"host:{self.HOST}\n"
            f"x-tc-action:{action.lower()}\n"
        )
        signed_headers = "content-type;host;x-tc-action"
        hashed_payload = self._hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
        credential_scope = f"{date}/{self.SERVICE}/tc3_request"
        hashed_canonical = self._hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical}"
        secret_date = self._sign(("TC3" + self._secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.SERVICE)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = self._hmac.new(secret_signing, string_to_sign.encode("utf-8"), self._hashlib.sha256).hexdigest()
        headers = {
            "Authorization": (
                f"TC3-HMAC-SHA256 Credential={self._secret_id}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.VERSION,
            "X-TC-Region": self._region,
        }
        r = requests.post(self.ENDPOINT, headers=headers, data=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "Error" in data.get("Response", {}):
            raise RuntimeError(data["Response"]["Error"])
        return data["Response"]

    def translate_batch(self, texts: Sequence[str]) -> List[str]:
        out: List[str] = []
        pending_idx: List[int] = []
        pending_texts: List[str] = []
        for i, t in enumerate(texts):
            s = t.strip()
            if not s or s.isdigit() or (s.startswith("http") and len(s) > 20):
                out.append(t)
            else:
                out.append("")
                pending_idx.append(i)
                pending_texts.append(t)
        if not pending_texts:
            return out
        CHUNK = 30
        for start in range(0, len(pending_texts), CHUNK):
            chunk_idx = pending_idx[start : start + CHUNK]
            chunk_texts = pending_texts[start : start + CHUNK]
            resp = self._call(
                "TextTranslateBatch",
                {"SourceTextList": chunk_texts, "Source": self._source,
                 "Target": self._target, "ProjectId": 0},
            )
            for idx, translated in zip(chunk_idx, resp.get("TargetTextList", [])):
                out[idx] = translated
        return out


# --------------------------------------------------------------------------- #
# 核心引擎
# --------------------------------------------------------------------------- #
class VectorPdfTranslator:
    def __init__(self, translate_fn: TranslatorFn, target_lang: str = "zh"):
        self._translate = translate_fn
        self.font_out = "china-s" if target_lang == "zh" else "helv"
        # 字宽测量：中文常/粗、英文常/粗 四个 Font
        self._fm_cn = fitz.Font(self.font_out)
        try:
            self._fm_cn_b = fitz.Font(fontfile=BOLD_CN_FONT)
        except Exception:
            self._fm_cn_b = self._fm_cn
        self._fm_en = fitz.Font("helv")
        self._fm_en_b = fitz.Font("hebo")

    # ---------- 提取 ----------
    def _collect_blocks(self, page: fitz.Page, m=None) -> List[Block]:
        blocks: List[Block] = []
        def T(r):
            r = fitz.Rect(r)
            if m == "swap":  # rot=90/270：x/y 互换，竖长条变横长条
                return fitz.Rect(r.y0, r.x0, r.y1, r.x1)
            if m:
                return r * m
            return r
        def TP(x, y):
            if m == "swap":
                return fitz.Point(y, x)
            if m:
                return fitz.Point(x, y) * m
            return fitz.Point(x, y)
        # 收集小图片（bullet 圆点）：直径 6-20pt 的独立小图
        bullet_rects: List[fitz.Rect] = []
        for info in page.get_image_info():
            r = fitz.Rect(info["bbox"])
            w, h = r.width, r.height
            if 5 <= w <= 25 and 5 <= h <= 25 and abs(w - h) < 5:
                bullet_rects.append(r)
        for raw in page.get_text("dict")["blocks"]:
            if raw["type"] != 0:
                continue
            blk = Block(bbox=tuple(T(raw["bbox"])))
            sizes: List[float] = []
            colors: List[int] = []
            for line in raw["lines"]:
                spans: List[Span] = []
                line_origins = []
                for sp in line["spans"]:
                    txt = sp["text"]
                    if not txt:
                        continue
                    fname = sp.get("font", "")
                    # 手写字（红色手写 OCR 层）：跳过，不翻译不擦
                    if fname.startswith(".SFUI") or fname.startswith(".PingFang"):
                        continue
                    is_math = any(fname.startswith(p) for p in
                                  ("CMSSI", "CMMI", "CMEX", "CMSY"))
                    sp_origin_y = float(sp["origin"][1])
                    spans.append(Span(
                        text=txt, bbox=tuple(T(sp["bbox"])),
                        size=float(sp["size"]), color=int(sp["color"]),
                        flags=int(sp["flags"]),
                        is_math=is_math, font_name=fname,
                        origin_y=sp_origin_y,
                    ))
                    line_origins.append((float(sp["size"]), sp_origin_y))
                    sizes.append(float(sp["size"]))
                    colors.append(int(sp["color"]))
                # 上下标判断：找这行最大字号 span 的 origin 作为基线
                if line_origins:
                    main_size = max(s for s, _ in line_origins)
                    main_origin = [y for s, y in line_origins if s == main_size][0]
                    for sp in spans:
                        if sp.size < main_size * 0.8 and sp.text.strip():
                            if sp.origin_y < main_origin - main_size * 0.1:
                                sp.is_sup = True
                            elif sp.origin_y > main_origin + main_size * 0.1:
                                sp.is_sub = True
                if spans:
                    blk.lines.append(spans)
                    blk.line_texts.append(line.get("text", "").strip())
                    orig = line["spans"][0]["origin"]
                    blk.line_baselines.append(TP(orig[0], orig[1]).y)
            if not blk.lines:
                continue
            sizes.sort()
            blk.main_size = sizes[len(sizes) // 2]
            blk.main_color = max(set(colors), key=colors.count)
            # 整段是否全粗体（标题/栏目标题）
            blk.is_all_bold = all(
                (s.flags & 16) for line in blk.lines for s in line
            ) and len(blk.lines) >= 1
            # bullet 检测：第一行 y 附近、x0 左边有圆点
            first_y0 = blk.bbox[1]
            first_y1 = blk.bbox[3]
            first_x0 = blk.bbox[0]
            for br in bullet_rects:
                # bullet 在文字 block 垂直范围内，且在文字左边或紧邻
                if br.y1 > first_y0 - 5 and br.y0 < first_y1 + 5:
                    if br.x1 < first_x0 + 15:  # 在文字左边或紧贴
                        blk.has_bullet = True
                        break
            # 数字编号检测：第一行第一个 span 以数字开头
            if blk.lines and blk.lines[0]:
                first_text = blk.lines[0][0].text.strip()
                if first_text and first_text[0].isdigit():
                    import re
                    # 匹配 "1." "2)" "3、" "4:" 或纯 "5xxx" 开头
                    if re.match(r'^\d+', first_text):
                        blk.has_numbering = True
            blocks.append(blk)
        return blocks

    # ---------- 跨 block 段落合并 ----------
    @staticmethod
    def _merge_blocks(blocks: List[Block]) -> List[Block]:
        """同栏相邻 block（字号/颜色一致、y 间距正常）合并。
        规则：
          1. 有 bullet 的 block 不与前一个合并（项目符号独立项）
          2. 只在相邻 block 间合并，不跳过中间 block
        """
        if len(blocks) <= 1:
            return blocks
        # 按栏（x0 聚类）再按 y0 排序
        blocks = sorted(blocks, key=lambda b: (round(b.bbox[0] / 20), b.bbox[1]))
        merged: List[Block] = [blocks[0]]
        for b in blocks[1:]:
            last = merged[-1]
            # 规则1：有 bullet 或数字编号的 block 独立，不合并
            if b.has_bullet or b.has_numbering:
                merged.append(b)
                continue
            same_col = abs(b.bbox[0] - last.bbox[0]) < 30
            same_size = abs(b.main_size - last.main_size) < 3.0
            same_color = b.main_color == last.main_color
            gap = b.bbox[1] - last.bbox[3]
            close = gap < last.main_size * 4.0
            if same_col and same_size and same_color and close:
                last.lines.extend(b.lines)
                last.line_texts.extend(b.line_texts)
                last.line_baselines.extend(b.line_baselines)
                last.bbox = (
                    min(last.bbox[0], b.bbox[0]), last.bbox[1],
                    max(last.bbox[2], b.bbox[2]), b.bbox[3],
                )
                last.bold_terms.extend(b.bold_terms)
            else:
                merged.append(b)
        return merged

    # ---------- 拼接文本（直接拼接 span text，空格 span 自带） ----------
    @staticmethod
    def _join_block_text(blk: Block) -> str:
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
                    flush_math()
                is_bold = bool(s.flags & 16)
                if is_bold and s.text.strip() and s.size < 16 and not s.is_math:
                    blk.bold_terms.append(s.text.strip())
            flush_math()
            if line_text.strip():
                parts.append(line_text.strip())
        return " ".join(parts)

    # ---------- 富文本 token 化：公式符号斜体 + 粗体术语标记 ----------
    @staticmethod
    def _tokenize_rich(text: str, bold_terms: List[str],
                       math_symbols: List[str]) -> List[Tuple[str, int]]:
        # flags: bit0=bold, bit1=math(斜体公式)
        tokens: List[Tuple[str, int]] = [(text, 0)]
        # 1) 在译文中搜索公式符号，标记 bit1（斜体）
        #    按长度降序，避免短符号先匹配吃掉长符号
        seen = set()
        for sym in sorted(set(math_symbols), key=len, reverse=True):
            if not sym or sym in seen:
                continue
            seen.add(sym)
            new_tokens: List[Tuple[str, int]] = []
            for t, fl in tokens:
                if fl & 1 or fl & 2:
                    new_tokens.append((t, fl)); continue
                pos = t.find(sym)
                if pos < 0:
                    new_tokens.append((t, fl)); continue
                if pos > 0:
                    new_tokens.append((t[:pos], fl))
                new_tokens.append((sym, fl | 2))
                rest = t[pos + len(sym):]
                if rest:
                    new_tokens.append((rest, fl))
            tokens = new_tokens
        # 2) 在译文中搜索粗体术语，标记 bit0
        for term in bold_terms:
            if not term:
                continue
            new_tokens: List[Tuple[str, int]] = []
            for t, fl in tokens:
                if fl & 1 or fl & 2:
                    new_tokens.append((t, fl)); continue
                pos = t.lower().find(term.lower())
                if pos < 0:
                    new_tokens.append((t, fl)); continue
                if pos > 0:
                    new_tokens.append((t[:pos], 0))
                new_tokens.append((t[pos:pos+len(term)], fl | 1))
                rest = t[pos+len(term):]
                if rest:
                    new_tokens.append((rest, fl))
            tokens = new_tokens
        return tokens

    # ---------- 字宽 ----------
    def _char_width(self, ch: str, flags: int, fontsize: float) -> float:
        bold = bool(flags & 1)
        if _is_cjk(ch):
            fm = self._fm_cn_b if bold else self._fm_cn
        else:
            fm = self._fm_en_b if bold else self._fm_en
        return fm.text_length(ch, fontsize=fontsize)

    # ---------- 富文本换行（按 token 换行，不拆字符） ----------
    def _wrap_rich(self, tokens: List[Tuple[str, int]],
                   max_width: float, fontsize: float
                   ) -> List[List[Tuple[str, int]]]:
        lines: List[List[Tuple[str, int]]] = [[]]
        cur_w = 0.0
        for text, flags in tokens:
            w = sum(self._char_width(ch, flags, fontsize) for ch in text)
            if cur_w + w <= max_width or not lines[-1]:
                # 第一个 token 也可能超宽，逐字符塞
                if not lines[-1] and w > max_width:
                    for ch in text:
                        cw = self._char_width(ch, flags, fontsize)
                        if cur_w + cw <= max_width or not lines[-1]:
                            lines[-1].append((ch, flags))
                            cur_w += cw
                        else:
                            lines.append([(ch, flags)])
                            cur_w = cw
                else:
                    lines[-1].append((text, flags))
                    cur_w += w
            else:
                # 放不下：逐字符塞，保证不丢字
                for ch in text:
                    cw = self._char_width(ch, flags, fontsize)
                    if cur_w + cw <= max_width:
                        lines[-1].append((ch, flags))
                        cur_w += cw
                    else:
                        lines.append([(ch, flags)])
                        cur_w = cw
        return [ln for ln in lines if ln]

    # ---------- 字号自适应 ----------
    def _fit(self, tokens: List[Tuple[str, int]],
             max_width: float, n_lines: int, base_size: float
             ) -> Tuple[float, List[List[Tuple[str, int]]]]:
        # 先试原字号，不行再缩放；下限是原字号的 60%
        floor = max(7.0, base_size * 0.6)
        size = base_size
        while size > floor:
            wrapped = self._wrap_rich(tokens, max_width, size)
            if len(wrapped) <= n_lines * 1.5:
                return size, wrapped
            size -= 1.0
        wrapped = self._wrap_rich(tokens, max_width, floor)
        # 不截断，多余的行往下排
        return floor, wrapped

    # ---------- 颜色 ----------
    @staticmethod
    def _rgb(c: int) -> Tuple[float, float, float]:
        return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

    # ---------- 段落绘制 ----------
    def _seg_width(self, seg: str, flags: int, fs: float) -> float:
        return sum(self._char_width(ch, flags, fs) for ch in seg)

    def _draw_seg(self, page, x: float, y: float, seg: str,
                  flags: int, fs: float, color, rot: int) -> None:
        if not seg:
            return
        has_cjk = any(_is_cjk(ch) for ch in seg)
        bold = bool(flags & 1)
        math = bool(flags & 2)
        if bold:
            if has_cjk:
                page.insert_text((x, y), seg, fontsize=fs, fontname="F0",
                                 fontfile=BOLD_CN_FONT, color=color)
            else:
                page.insert_text((x, y), seg, fontsize=fs, fontname="hebo",
                                 color=color)
        elif math:
            # 公式符号：用斜体英文字体
            page.insert_text((x, y), seg, fontsize=fs,
                             fontname="heit", color=color)
        else:
            if has_cjk:
                page.insert_text((x, y), seg, fontsize=fs,
                                 fontname=self.font_out, color=color)
            else:
                page.insert_text((x, y), seg, fontsize=fs,
                                 fontname="helv", color=color)

    # ---------- 单页 ----------
    def translate_page(self, page: fitz.Page) -> int:
        rot = 0
        raw_blocks = self._collect_blocks(page)
        blocks = self._merge_blocks(raw_blocks)
        if not blocks:
            return 0

        originals = [self._join_block_text(b) for b in blocks]
        translated = self._translate(originals)

        # 擦除原文
        for b in blocks:
            for line in b.lines:
                for s in line:
                    page.add_redact_annot(fitz.Rect(s.bbox))
        for kw in (
            {"images": fitz.PDF_REDACT_IMAGE_NONE,
             "graphics": fitz.PDF_REDACT_LINE_ART_NONE},
            {"images": fitz.PDF_REDACT_IMAGE_NONE},
            {},
        ):
            try:
                page.apply_redactions(**kw)
                break
            except TypeError:
                continue
            except Exception:
                break

        # 写回：整段译文 + 搜索数学表达式标记斜体
        n_written = 0
        for blk, new_text in zip(blocks, translated):
            if not new_text.strip():
                continue
            tokens = self._tokenize_rich(new_text, blk.bold_terms, blk.math_symbols)
            if blk.is_all_bold:
                tokens = [(t, fl | 1) for t, fl in tokens]
            if not tokens:
                continue
            x0, y0, x1, y1 = blk.bbox
            max_w = (x1 - x0) * 0.9  # 留 10% 余量，防止测量误差导致溢出
            n_orig = len(blk.line_baselines)
            fit_size, wrapped = self._fit(tokens, max_w, n_orig, blk.main_size)
            color = self._rgb(blk.main_color)
            for i, line_tokens in enumerate(wrapped):
                if i < len(blk.line_baselines):
                    y = blk.line_baselines[i]
                else:
                    # 多余的行往下排，行距按字号算
                    y = blk.line_baselines[-1] + (i - len(blk.line_baselines) + 1) * fit_size * 1.3
                x = x0
                for text, fl in line_tokens:
                    self._draw_seg(page, x, y, text, fl, fit_size, color, rot)
                    x += self._seg_width(text, fl, fit_size)
                n_written += 1
        return n_written

    # ---------- 入口 ----------
    def run(self, src: str, dst: str) -> None:
        doc = fitz.open(src)
        n_pages = doc.page_count
        total = 0
        for page in doc:
            # rotation != 0 的页：清零 rotation，让 dict 坐标和 insert_text 坐标系一致；
            # 不恢复 rotation，输出就是字正的（页面可能变纵向，但字方向对）。
            if page.rotation:
                page.set_rotation(0)
            total += self.translate_page(page)
        doc.save(dst, garbage=3, deflate=True)
        doc.close()
        print(f"[OK] {src} → {dst}  共 {n_pages} 页 / 写入 {total} 行译文")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="PDF 段落翻译 v3")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--to", dest="dst_lang", default="zh")
    ap.add_argument("--engine", choices=["mock", "tencent"], default="mock")
    args = ap.parse_args(argv)

    if args.engine == "tencent":
        fn = TencentTranslator("en", args.dst_lang).translate_batch
    else:
        fn = MockTranslator().translate_batch
    VectorPdfTranslator(fn, target_lang=args.dst_lang).run(args.src, args.dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
