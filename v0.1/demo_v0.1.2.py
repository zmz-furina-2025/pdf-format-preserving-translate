"""
demo_v0.1.2.py — block 级段落合并
同 block 内 line 拼成整段翻译，按宽度回换行。
伪翻译：中文占位文本。无跨 block 合并、无粗体、无腾讯、无背景保留。
"""
from __future__ import annotations
import argparse, sys
from dataclasses import dataclass, field
from typing import List, Tuple
import fitz


@dataclass
class Block:
    bbox: Tuple[float, float, float, float]
    lines: List[List[str]] = field(default_factory=list)
    main_size: float = 11.0
    main_color: int = 0
    baselines: List[float] = field(default_factory=list)


class MockTranslator:
    _POOL = "这是一段用于验证排版还原效果的占位译文，中文宽度和换行行为将在渲染后人工检查。"
    def translate_batch(self, texts: List[str]) -> List[str]:
        out = []
        for t in texts:
            s = t.strip()
            if not s or s.isdigit() or s.startswith("http"):
                out.append(t); continue
            n = max(10, int(len(s) * 0.55))
            out.append((self._POOL * (n // len(self._POOL) + 1))[:n])
        return out


class Translator:
    def __init__(self, fn):
        self._t = fn
        self.fm = fitz.Font("china-s")

    @staticmethod
    def _rgb(c):
        return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

    def _collect(self, page):
        blocks = []
        for raw in page.get_text("dict")["blocks"]:
            if raw["type"] != 0: continue
            blk = Block(bbox=tuple(raw["bbox"]))
            sizes, colors = [], []
            for line in raw["lines"]:
                txt = "".join(sp["text"] for sp in line["spans"]).strip()
                if not txt: continue
                blk.lines.append([txt])
                y0, y1 = line["bbox"][1], line["bbox"][3]
                blk.baselines.append(y1 - 0.22 * (y1 - y0))
                for sp in line["spans"]:
                    sizes.append(float(sp["size"])); colors.append(int(sp["color"]))
            if not blk.lines: continue
            sizes.sort(); blk.main_size = sizes[len(sizes)//2]
            blk.main_color = max(set(colors), key=colors.count)
            blocks.append(blk)
        return blocks

    def _wrap(self, text, max_w, fs):
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        if cjk > len(text) * 0.25:
            lines, cur = [], ""
            for ch in text:
                if self.fm.text_length(cur+ch, fontsize=fs) <= max_w: cur += ch
                else: lines.append(cur); cur = ch
            if cur: lines.append(cur)
            return lines or [text]
        lines, cur = [], ""
        for w in text.split(" "):
            trial = f"{cur} {w}".strip() if cur else w
            if self.fm.text_length(trial, fontsize=fs) <= max_w: cur = trial
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines or [text]

    def _fit(self, text, max_w, n_lines, base):
        size = base
        while size > 4:
            w = self._wrap(text, max_w, size)
            if len(w) <= n_lines: return size, w
            size -= 0.5
        return 4.0, self._wrap(text, max_w, 4)[:n_lines]

    def page(self, page):
        blocks = self._collect(page)
        if not blocks: return 0
        originals = [" ".join(" ".join(l) for l in b.lines) for b in blocks]
        translated = self._t(originals)
        for b in blocks:
            page.add_redact_annot(fitz.Rect(b.bbox), fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        n = 0
        for b, txt in zip(blocks, translated):
            x0, y0, x1, y1 = b.bbox
            size, wrapped = self._fit(txt, x1-x0, len(b.baselines), b.main_size)
            for i, line in enumerate(wrapped):
                y = b.baselines[i] if i < len(b.baselines) else b.baselines[-1]+i*16
                page.insert_text((x0, y), line, fontsize=size,
                                 fontname="china-s", color=self._rgb(b.main_color))
                n += 1
        return n

    def run(self, src, dst):
        doc = fitz.open(src)
        total = sum(self.page(p) for p in doc)
        doc.save(dst, garbage=3, deflate=True); doc.close()
        print(f"[OK] {src} -> {dst}  {total} 行")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("dst")
    a = ap.parse_args()
    Translator(MockTranslator().translate_batch).run(a.src, a.dst)
