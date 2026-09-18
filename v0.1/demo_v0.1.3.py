"""
demo_v0.1.3.py — 跨 block 合并 + 腾讯 API + 粗体术语对齐（早期版）
相对 v0.1.2：
  + 跨 block 段落合并
  + 腾讯云 TMT 真实翻译
  + span.origin[1] 精确基线
  + 粗体术语对齐（翻译后在译文中搜原文标粗）
未修：全粗体 block（标题）不处理、粗体英文字距、CJK 标点变中点。
"""
from __future__ import annotations
import argparse, os, re, sys
from dataclasses import dataclass, field
from typing import Callable, List, Sequence, Tuple
import fitz


def _load_env(path=".env"):
    if not os.path.exists(path): return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
_load_env()


@dataclass
class Span:
    text: str
    bbox: Tuple[float, float, float, float]
    size: float
    color: int
    flags: int = 0


@dataclass
class Block:
    bbox: Tuple[float, float, float, float]
    lines: List[List[Span]] = field(default_factory=list)
    main_size: float = 11.0
    main_color: int = 0
    baselines: List[float] = field(default_factory=list)
    bold_terms: List[str] = field(default_factory=list)


class MockTranslator:
    _POOL = "这是一段用于验证排版还原效果的占位译文，中文宽度和换行行为将在渲染后人工检查。"
    def translate_batch(self, texts):
        out = []
        for t in texts:
            s = t.strip()
            if not s or s.isdigit() or s.startswith("http"): out.append(t); continue
            n = max(10, int(len(s)*0.55))
            out.append((self._POOL*(n//len(self._POOL)+1))[:n])
        return out


class TencentTranslator:
    HOST = "tmt.tencentcloudapi.com"; ENDPOINT = "https://tmt.tencentcloudapi.com"
    def __init__(self, src="en", dst="zh"):
        import hashlib, hmac, time
        self._hmac, self._hashlib, self._time = hmac, hashlib, time
        self._sid = os.environ["TENCENT_SECRET_ID"]
        self._skey = os.environ["TENCENT_SECRET_KEY"]
        self._region = os.environ.get("TENCENT_REGION", "ap-shanghai")
        self._src, self._dst = src, dst
    def _sign(self, key, msg):
        return self._hmac.new(key, msg.encode(), self._hashlib.sha256).digest()
    def _call(self, action, payload):
        import json, requests
        ts = int(self._time.time()); date = self._time.strftime("%Y-%m-%d", self._time.gmtime(ts))
        body = json.dumps(payload)
        ch = f"content-type:application/json; charset=utf-8\nhost:{self.HOST}\nx-tc-action:{action.lower()}\n"
        sh = "content-type;host;x-tc-action"
        hp = self._hashlib.sha256(body.encode()).hexdigest()
        cr = f"POST\n/\n\n{ch}\n{sh}\n{hp}"
        cs = f"{date}/tmt/tc3_request"
        sts = f"TC3-HMAC-SHA256\n{ts}\n{cs}\n{self._hashlib.sha256(cr.encode()).hexdigest()}"
        sd = self._sign(("TC3"+self._skey).encode(), date)
        ss = self._sign(sd, "tmt")
        ssg = self._sign(ss, "tc3_request")
        sig = self._hmac.new(ssg, sts.encode(), self._hashlib.sha256).hexdigest()
        headers = {
            "Authorization": f"TC3-HMAC-SHA256 Credential={self._sid}/{cs}, SignedHeaders={sh}, Signature={sig}",
            "Content-Type": "application/json; charset=utf-8", "Host": self.HOST,
            "X-TC-Action": action, "X-TC-Timestamp": str(ts),
            "X-TC-Version": "2018-03-21", "X-TC-Region": self._region,
        }
        r = requests.post(self.ENDPOINT, headers=headers, data=body, timeout=30)
        r.raise_for_status()
        d = r.json()
        if "Error" in d.get("Response", {}): raise RuntimeError(d["Response"]["Error"])
        return d["Response"]
    def translate_batch(self, texts):
        out = []; pending_i = []; pending_t = []
        for i, t in enumerate(texts):
            s = t.strip()
            if not s or s.isdigit() or s.startswith("http"): out.append(t)
            else: out.append(""); pending_i.append(i); pending_t.append(t)
        if not pending_t: return out
        for st in range(0, len(pending_t), 30):
            ci = pending_i[st:st+30]; ct = pending_t[st:st+30]
            r = self._call("TextTranslateBatch", {"SourceTextList": ct, "Source": self._src, "Target": self._dst, "ProjectId": 0})
            for i, t in zip(ci, r.get("TargetTextList", [])): out[i] = t
        return out


class Translator:
    def __init__(self, fn):
        self._t = fn
        self.fm = fitz.Font("china-s")
        try: self.fm_b = fitz.Font(fontfile=r"C:\Windows\Fonts\msyhbd.ttc")
        except: self.fm_b = self.fm

    def _collect(self, page):
        blocks = []
        for raw in page.get_text("dict")["blocks"]:
            if raw["type"] != 0: continue
            blk = Block(bbox=tuple(raw["bbox"]))
            sizes, colors = [], []
            for line in raw["lines"]:
                spans = []
                for sp in line["spans"]:
                    if not sp["text"].strip(): continue
                    spans.append(Span(sp["text"], tuple(sp["bbox"]), float(sp["size"]), int(sp["color"]), int(sp["flags"])))
                    sizes.append(float(sp["size"])); colors.append(int(sp["color"]))
                if spans:
                    blk.lines.append(spans)
                    blk.baselines.append(float(line["spans"][0]["origin"][1]))
            if not blk.lines: continue
            sizes.sort(); blk.main_size = sizes[len(sizes)//2]
            blk.main_color = max(set(colors), key=colors.count)
            blocks.append(blk)
        return blocks

    @staticmethod
    def _merge(blocks):
        if len(blocks) <= 1: return blocks
        blocks = sorted(blocks, key=lambda b: (round(b.bbox[0]/20), b.bbox[1]))
        out = [blocks[0]]
        for b in blocks[1:]:
            last = out[-1]
            if (abs(b.bbox[0]-last.bbox[0]) < 30 and abs(b.main_size-last.main_size) < 1.5
                and b.main_color == last.main_color and b.bbox[1]-last.bbox[3] < last.main_size*2.5):
                last.lines.extend(b.lines); last.baselines.extend(b.baselines)
                last.bbox = (min(last.bbox[0],b.bbox[0]), last.bbox[1], max(last.bbox[2],b.bbox[2]), b.bbox[3])
                last.bold_terms.extend(b.bold_terms)
            else: out.append(b)
        return out

    @staticmethod
    def _join(blk):
        parts = []
        for line in blk.lines:
            lp = []
            for s in line:
                lp.append(s.text)
                if (s.flags & 16) and s.text.strip() and s.size < 16:
                    blk.bold_terms.append(s.text.strip())
            parts.append("".join(lp).strip())
        return " ".join(p for p in parts if p)

    @staticmethod
    def _tokenize(text, terms):
        tokens = [(text, False)]
        for term in terms:
            if not term: continue
            new = []
            for t, b in tokens:
                if b: new.append((t, b)); continue
                pos = t.lower().find(term.lower())
                if pos < 0: new.append((t, b)); continue
                if pos > 0: new.append((t[:pos], False))
                new.append((t[pos:pos+len(term)], True))
                if pos+len(term) < len(t): new.append((t[pos+len(term):], False))
            tokens = new
        return tokens

    @staticmethod
    def _rgb(c):
        return ((c>>16&255)/255, (c>>8&255)/255, (c&255)/255)

    def _wrap(self, tokens, max_w, fs):
        lines, cw = [[]], 0.0
        for text, bold in tokens:
            for ch in text:
                fm = self.fm_b if bold else self.fm
                w = fm.text_length(ch, fontsize=fs)
                if cw + w <= max_w or not lines[-1]:
                    lines[-1].append((ch, bold)); cw += w
                else:
                    lines.append([(ch, bold)]); cw = w
        return [l for l in lines if l]

    def _fit(self, tokens, max_w, n, base):
        size = base
        while size > 4:
            w = self._wrap(tokens, max_w, size)
            if len(w) <= n: return size, w
            size -= 0.5
        return 4.0, self._wrap(tokens, max_w, 4)[:n]

    def page(self, page):
        blocks = self._merge(self._collect(page))
        if not blocks: return 0
        originals = [self._join(b) for b in blocks]
        translated = self._t(originals)
        for b in blocks:
            for line in b.lines:
                for s in line:
                    page.add_redact_annot(fitz.Rect(s.bbox), fill=(1,1,1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        n = 0
        for b, txt in zip(blocks, translated):
            if not txt.strip(): continue
            tokens = self._tokenize(txt, b.bold_terms)
            x0, y0, x1, y1 = b.bbox
            size, wrapped = self._fit(tokens, x1-x0, len(b.baselines), b.main_size)
            color = self._rgb(b.main_color)
            for i, line in enumerate(wrapped):
                y = b.baselines[i] if i < len(b.baselines) else b.baselines[-1]+i*16
                x = x0
                for ch, bold in line:
                    if bold:
                        page.insert_text((x,y), ch, fontsize=size, fontname="F0", fontfile=r"C:\Windows\Fonts\msyhbd.ttc", color=color)
                        x += self.fm_b.text_length(ch, fontsize=size)
                    else:
                        page.insert_text((x,y), ch, fontsize=size, fontname="china-s", color=color)
                        x += self.fm.text_length(ch, fontsize=size)
                n += 1
        return n

    def run(self, src, dst):
        doc = fitz.open(src)
        total = sum(self.page(p) for p in doc)
        doc.save(dst, garbage=3, deflate=True); doc.close()
        print(f"[OK] {src} -> {dst}  {total} 行")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--engine", choices=["mock","tencent"], default="mock")
    a = ap.parse_args()
    fn = TencentTranslator().translate_batch if a.engine == "tencent" else MockTranslator().translate_batch
    Translator(fn).run(a.src, a.dst)
