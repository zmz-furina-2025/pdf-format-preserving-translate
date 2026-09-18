"""
demo_v0.1.1.py — span 级替换
每个文字片段单独翻译塞回原位置，无段落合并。
伪翻译：【译】+ 大写。
"""
from __future__ import annotations
import argparse, sys
from dataclasses import dataclass
from typing import List, Tuple
import fitz


@dataclass
class Span:
    text: str
    bbox: Tuple[float, float, float, float]
    size: float
    color: int


class MockTranslator:
    def translate_batch(self, texts: List[str]) -> List[str]:
        out = []
        for t in texts:
            s = t.strip()
            if not s or s.isdigit() or (s.startswith("http") and len(s) > 20):
                out.append(t); continue
            out.append(f"【译】{t.upper()}")
        return out


class Translator:
    def __init__(self, fn):
        self._t = fn
        self.fm = fitz.Font("china-s")

    @staticmethod
    def _rgb(c):
        return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

    def page(self, page):
        spans = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0: continue
            for line in b["lines"]:
                for sp in line["spans"]:
                    if sp["text"].strip():
                        spans.append(Span(sp["text"], tuple(sp["bbox"]),
                                          float(sp["size"]), int(sp["color"])))
        if not spans: return 0
        translated = self._t([s.text for s in spans])
        for s in spans:
            page.add_redact_annot(fitz.Rect(s.bbox), fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for s, txt in zip(spans, translated):
            x0, y0, x1, y1 = s.bbox
            size = s.size
            while size > 4 and self.fm.text_length(txt, fontsize=size) > x1 - x0:
                size -= 0.5
            page.insert_text((x0, y1 - 0.22 * (y1 - y0)), txt,
                             fontsize=size, fontname="china-s",
                             color=self._rgb(s.color))
        return len(spans)

    def run(self, src, dst):
        doc = fitz.open(src)
        total = sum(self.page(p) for p in doc)
        doc.save(dst, garbage=3, deflate=True); doc.close()
        print(f"[OK] {src} -> {dst}  {total} 片段")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("dst")
    a = ap.parse_args()
    Translator(MockTranslator().translate_batch).run(a.src, a.dst)
