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
def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


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
    def _collect_blocks(self, page: fitz.Page) -> List[Block]:
        blocks: List[Block] = []
        for raw in page.get_text("dict")["blocks"]:
            if raw["type"] != 0:
                continue
            blk = Block(bbox=tuple(raw["bbox"]))
            sizes: List[float] = []
            colors: List[int] = []
            for line in raw["lines"]:
                spans: List[Span] = []
                for sp in line["spans"]:
                    txt = sp["text"]
                    if not txt or not txt.strip():
                        continue
                    spans.append(Span(
                        text=txt, bbox=tuple(sp["bbox"]),
                        size=float(sp["size"]), color=int(sp["color"]),
                        flags=int(sp["flags"]),
                    ))
                    sizes.append(float(sp["size"]))
                    colors.append(int(sp["color"]))
                if spans:
                    blk.lines.append(spans)
                    # 用该行第一个 span 的真实基线（PyMuPDF span.origin[1]）
                    blk.line_baselines.append(float(line["spans"][0]["origin"][1]))
            if not blk.lines:
                continue
            sizes.sort()
            blk.main_size = sizes[len(sizes) // 2]
            blk.main_color = max(set(colors), key=colors.count)
            # 整段是否全粗体（标题/栏目标题）
            blk.is_all_bold = all(
                (s.flags & 16) for line in blk.lines for s in line
            ) and len(blk.lines) >= 1
            blocks.append(blk)
        return blocks

    # ---------- 跨 block 段落合并 ----------
    @staticmethod
    def _merge_blocks(blocks: List[Block]) -> List[Block]:
        """同栏相邻 block（字号/颜色一致、y 间距正常）合并。"""
        if len(blocks) <= 1:
            return blocks
        # 按栏（x0 聚类）再按 y0 排序
        blocks = sorted(blocks, key=lambda b: (round(b.bbox[0] / 20), b.bbox[1]))
        merged: List[Block] = [blocks[0]]
        for b in blocks[1:]:
            last = merged[-1]
            same_col = abs(b.bbox[0] - last.bbox[0]) < 30
            same_size = abs(b.main_size - last.main_size) < 1.5
            same_color = b.main_color == last.main_color
            gap = b.bbox[1] - last.bbox[3]
            close = gap < last.main_size * 2.5
            if same_col and same_size and same_color and close:
                last.lines.extend(b.lines)
                last.line_baselines.extend(b.line_baselines)
                last.bbox = (
                    min(last.bbox[0], b.bbox[0]), last.bbox[1],
                    max(last.bbox[2], b.bbox[2]), b.bbox[3],
                )
                last.bold_terms.extend(b.bold_terms)
            else:
                merged.append(b)
        return merged

    # ---------- 拼接文本（记录粗体术语，不送占位符） ----------
    @staticmethod
    def _join_block_text(blk: Block) -> str:
        parts = []
        for line in blk.lines:
            line_parts = []
            for s in line:
                line_parts.append(s.text)
                is_bold = bool(s.flags & 16)
                # 小字号粗体 span 记为术语，翻译后在译文中搜索标粗
                if is_bold and s.text.strip() and s.size < 16:
                    blk.bold_terms.append(s.text.strip())
            parts.append("".join(line_parts).strip())
        return " ".join(p for p in parts if p)

    # ---------- 富文本 token 化：在译文中搜索粗体术语 ----------
    @staticmethod
    def _tokenize_rich(text: str, bold_terms: List[str]) -> List[Tuple[str, bool]]:
        tokens: List[Tuple[str, bool]] = [(text, False)]
        lower_text = text.lower()
        for term in bold_terms:
            if not term:
                continue
            idx = lower_text.find(term.lower())
            if idx < 0:
                continue
            new_tokens: List[Tuple[str, bool]] = []
            for t, is_b in tokens:
                if is_b:
                    new_tokens.append((t, is_b))
                    continue
                pos = t.lower().find(term.lower())
                if pos < 0:
                    new_tokens.append((t, is_b))
                    continue
                if pos > 0:
                    new_tokens.append((t[:pos], False))
                new_tokens.append((t[pos : pos + len(term)], True))
                rest = t[pos + len(term) :]
                if rest:
                    new_tokens.append((rest, False))
            tokens = new_tokens
        return tokens

    # ---------- 字宽 ----------
    def _char_width(self, ch: str, is_bold: bool, fontsize: float) -> float:
        if _is_cjk(ch):
            fm = self._fm_cn_b if is_bold else self._fm_cn
        else:
            fm = self._fm_en_b if is_bold else self._fm_en
        return fm.text_length(ch, fontsize=fontsize)

    # ---------- 富文本换行 ----------
    def _wrap_rich(self, tokens: List[Tuple[str, bool]],
                   max_width: float, fontsize: float
                   ) -> List[List[Tuple[str, bool]]]:
        lines: List[List[Tuple[str, bool]]] = [[]]
        cur_w = 0.0
        for text, is_bold in tokens:
            for ch in text:
                w = self._char_width(ch, is_bold, fontsize)
                if cur_w + w <= max_width or not lines[-1]:
                    lines[-1].append((ch, is_bold))
                    cur_w += w
                else:
                    lines.append([(ch, is_bold)])
                    cur_w = w
        return [ln for ln in lines if ln]

    # ---------- 字号自适应 ----------
    def _fit(self, tokens: List[Tuple[str, bool]],
             max_width: float, n_lines: int, base_size: float
             ) -> Tuple[float, List[List[Tuple[str, bool]]]]:
        size = base_size
        while size > 4.0:
            wrapped = self._wrap_rich(tokens, max_width, size)
            if len(wrapped) <= n_lines:
                return size, wrapped
            size -= 0.5
        wrapped = self._wrap_rich(tokens, max_width, 4.0)
        if len(wrapped) > n_lines:
            wrapped = wrapped[:n_lines]
        return 4.0, wrapped

    # ---------- 颜色 ----------
    @staticmethod
    def _rgb(c: int) -> Tuple[float, float, float]:
        return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

    # ---------- 单页 ----------
    def translate_page(self, page: fitz.Page) -> int:
        raw_blocks = self._collect_blocks(page)
        blocks = self._merge_blocks(raw_blocks)
        if not blocks:
            return 0

        originals = [self._join_block_text(b) for b in blocks]
        translated = self._translate(originals)

        # 擦除：涂白（v0.1 只处理白底纯文字，不支持色块/图片背景）
        for b in blocks:
            for line in b.lines:
                for s in line:
                    page.add_redact_annot(fitz.Rect(s.bbox), fill=(1, 1, 1))
        for kw in ({"images": fitz.PDF_REDACT_IMAGE_NONE}, {"images": 2}, {}):
            try:
                page.apply_redactions(**kw)
                break
            except TypeError:
                continue
            except Exception:
                break

        # 写回（逐字符，粗体用粗体字体）
        n_written = 0
        for blk, new_text in zip(blocks, translated):
            if not new_text.strip():
                continue
            tokens = self._tokenize_rich(new_text, blk.bold_terms)
            # 整段粗体 block（标题/栏目标题）：所有 token 标粗
            if blk.is_all_bold:
                tokens = [(t, True) for t, _ in tokens]
            if not tokens:
                continue
            x0, y0, x1, y1 = blk.bbox
            max_w = x1 - x0
            n_orig = len(blk.line_baselines)
            fit_size, wrapped = self._fit(tokens, max_w, n_orig, blk.main_size)
            color = self._rgb(blk.main_color)
            for i, line_tokens in enumerate(wrapped):
                if i < len(blk.line_baselines):
                    y = blk.line_baselines[i]
                else:
                    y = blk.line_baselines[-1] + (i - len(blk.line_baselines) + 1) * 16
                x = x0
                for ch, is_bold in line_tokens:
                    # 按字符选字体：粗体中文用雅黑粗，粗体英文用 hebo；
                    # 常规中文用 china-s，常规英文用 helv
                    if is_bold:
                        if _is_cjk(ch):
                            page.insert_text(
                                (x, y), ch, fontsize=fit_size,
                                fontname="F0", fontfile=BOLD_CN_FONT, color=color,
                            )
                        else:
                            page.insert_text(
                                (x, y), ch, fontsize=fit_size,
                                fontname="hebo", color=color,
                            )
                    else:
                        if _is_cjk(ch):
                            page.insert_text(
                                (x, y), ch, fontsize=fit_size,
                                fontname=self.font_out, color=color,
                            )
                        else:
                            page.insert_text(
                                (x, y), ch, fontsize=fit_size,
                                fontname="helv", color=color,
                            )
                    x += self._char_width(ch, is_bold, fit_size)
                n_written += 1
        return n_written

    # ---------- 入口 ----------
    def run(self, src: str, dst: str) -> None:
        doc = fitz.open(src)
        n_pages = doc.page_count
        total = 0
        for page in doc:
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
