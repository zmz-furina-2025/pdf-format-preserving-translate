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
    # 缩写符号（如 r.v., i.i.d.），不翻译，直接保留
    abbrev_symbols: List[str] = field(default_factory=list)
    # 上标/下标字符（如 a₁ 的 1，x² 的 2）
    sup_symbols: List[str] = field(default_factory=list)
    sub_symbols: List[str] = field(default_factory=list)
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

# TODO: 术语表方案（被注释，待换支持 keep 标签的翻译 API 后启用）
# GLOSSARY = {
#     "r.v.": "随机变量",
#     "i.i.d.": "独立同分布",
#     "p.m.f.": "概率质量函数",
#     "c.d.f.": "累积分布函数",
# }
# _GLOSSARY_MAP = {}
# for i, (k, v) in enumerate(GLOSSARY.items()):
#     placeholder = f"⟦TERM{i}⟧"
#     _GLOSSARY_MAP[placeholder] = (k, v)


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


class QwenTranslator:
    """本地 Qwen 模型（通过 Ollama HTTP API 调用）。"""
    def __init__(self, source: str = "en", target: str = "zh",
                 model: str = "qwen2.5:latest", host: str = "http://localhost:11434"):
        self._source = source
        self._target = target
        self._model = model
        self._host = host

    def translate_batch(self, texts: Sequence[str]) -> List[str]:
        import requests
        out: List[str] = []
        for t in texts:
            s = t.strip()
            if not s:
                out.append(t)
                continue
            prompt = f"""Translate the following academic text from English to Chinese.
Rules:
1. Keep ALL math formulas EXACTLY as they are, wrapped in \\(...\\). Do NOT modify, split, or reorder formulas. For example: \\(\\sum_{{j=1}}^{{\\infty}} p_X(x_j) = 1\\), \\(P(X=x)\\), \\(a_1, a_2, \\ldots\\).
2. Do NOT repeat formulas. Translate the text ONCE.
3. Keep abbreviations like r.v., i.i.d. unchanged.
4. Output ONLY the Chinese translation, nothing else.

Text: {t}"""
            try:
                resp = requests.post(
                    f"{self._host}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1},
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                result = resp.json().get("response", "").strip()
                print(f"[qwen] in: {s[:60]}")
                print(f"[qwen] out: {result[:80]}")
                out.append(result if result else t)
            except Exception as e:
                print(f"[qwen] translation failed: {e}")
                out.append(t)
        return out


# --------------------------------------------------------------------------- #
# 核心引擎
# --------------------------------------------------------------------------- #
class VectorPdfTranslator:
    def __init__(self, translate_fn: TranslatorFn, target_lang: str = "zh",
                 use_cache: bool = True, cache_path: str = "translate_cache.json",
                 use_layout_ai: bool = False, render_math: bool = True):
        self._translate = translate_fn
        self._render_math = render_math
        self.font_out = "china-s" if target_lang == "zh" else "helv"
        # 字宽测量：中文常/粗、英文常/粗 四个 Font
        self._fm_cn = fitz.Font(self.font_out)
        try:
            self._fm_cn_b = fitz.Font(fontfile=BOLD_CN_FONT)
        except Exception:
            self._fm_cn_b = self._fm_cn
        self._fm_en = fitz.Font("helv")
        self._fm_en_b = fitz.Font("hebo")
        self._fm_en_i = fitz.Font("heit")  # 斜体英文字体
        # 翻译缓存
        self._use_cache = use_cache
        self._cache_path = cache_path
        self._cache: dict = {}
        if use_cache and os.path.exists(cache_path):
            try:
                import json
                with open(cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}
        # 版面 AI 检测（可选，需要装 doclayout-yolo）
        self._use_layout_ai = use_layout_ai
        self._layout_model = None
        if use_layout_ai:
            try:
                from doclayout_yolo import YOLOv10
                model_path = os.path.join(os.path.dirname(__file__),
                    "doclayout_yolo_docstructbench_imgsz1024.onnx")
                self._layout_model = YOLOv10(model_path, task="detect")
                print("[layout-ai] DocLayout-YOLO loaded")
            except Exception as e:
                print(f"[layout-ai] 加载失败，回退到坐标聚类: {e}")
                self._use_layout_ai = False

    def _cached_translate(self, texts: List[str]) -> List[str]:
        """带缓存的批量翻译"""
        if not self._use_cache:
            return self._translate(texts)
        import hashlib
        import json
        out: List[str] = [""] * len(texts)
        pending_idx: List[int] = []
        pending_texts: List[str] = []
        for i, t in enumerate(texts):
            key = hashlib.md5(t.encode("utf-8")).hexdigest()
            if key in self._cache:
                out[i] = self._cache[key]
            else:
                pending_idx.append(i)
                pending_texts.append(t)
        if pending_texts:
            results = self._translate(pending_texts)
            for idx, res in zip(pending_idx, results):
                out[idx] = res
                key = hashlib.md5(texts[idx].encode("utf-8")).hexdigest()
                self._cache[key] = res
            # 写回缓存
            try:
                with open(self._cache_path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=1)
            except Exception:
                pass
        return out

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
    def _merge_blocks(self, blocks: List[Block]) -> List[Block]:
        """同栏相邻 block（字号/颜色一致、y 间距正常）合并。
        规则：
          1. 有 bullet 的 block 不与前一个合并（项目符号独立项）
          2. 只在相邻 block 间合并，不跳过中间 block
          3. 两个 block 之间有 AI 检测到的障碍物（figure/table）时不合并
        """
        if len(blocks) <= 1:
            return blocks
        # 按 y0 排序（从上到下），同一 y 范围内按 x0 排序（从左到右）
        blocks = sorted(blocks, key=lambda b: (round(b.bbox[1] / 30), b.bbox[0]))
        merged: List[Block] = [blocks[0]]
        for b in blocks[1:]:
            last = merged[-1]
            # 规则1：有 bullet 或数字编号的 block 独立，不合并
            if b.has_bullet or b.has_numbering:
                merged.append(b)
                continue
            same_col = abs(b.bbox[0] - last.bbox[0]) < 30
            same_size = abs(b.main_size - last.main_size) < 3.0
            # 颜色：放宽判断，RGB 差在 30 以内就算同色（公式 span 可能偏色）
            c1 = b.main_color
            c2 = last.main_color
            r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
            r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
            same_color = abs(r1-r2) < 30 and abs(g1-g2) < 30 and abs(b1-b2) < 30
            gap = b.bbox[1] - last.bbox[3]
            # gap 可能为负（两个 block 上下重叠），但重叠不能太多
            # 正文里两个行 block 上下重叠一点点（gap ~ -main_size），可以合并
            # 封面页的居中 block 上下重叠很多（gap ~ -8*main_size），不合并
            close = -last.main_size * 4.0 < gap < last.main_size * 4.0
            # 调试：打印每个 block 的合并判断
            print(f"  [merge] b='{self._join_block_text(b)[:40]}' "
                  f"same_col={same_col} same_size={same_size}({b.main_size:.1f}vs{last.main_size:.1f}) "
                  f"same_color={same_color} close={close}({gap:.1f}) "
                  f"bullet={b.has_bullet} num={b.has_numbering}")
            # 规则3：两个 block 之间有障碍物（figure/table）时不合并
            has_obstacle = False
            for obs in self._layout_obstacles:
                # 障碍物在两个 block 的 y 之间
                if obs.y0 > last.bbox[3] - 5 and obs.y1 < b.bbox[1] + 5:
                    has_obstacle = True
                    break
            if same_col and same_size and same_color and close and not has_obstacle:
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
            # 找这行的求和符号 span（CMSY 字体的 1/2/4）
            sum_spans = [s for s in line if s.font_name.startswith('CMSY') and s.text in ('1', '2', '4')]
            processed = set()
            for s in line:
                # 如果是求和符号，找到它的上下标
                if s in sum_spans and id(s) not in processed:
                    sub_spans = []
                    sup_spans = []
                    # 在所有行找上下标
                    print(f"[sum]   blk.lines count: {len(blk.lines)}")
                    for li, line in enumerate(blk.lines):
                        print(f"[sum]   line {li}: {[s.text for s in line]}")
                        for other in other_line:
                            if other is s:
                                continue
                            print(f"[sum]   other: {other.text}, x0={other.bbox[0]:.1f}, x1={other.bbox[2]:.1f}, cy={(other.bbox[1]+other.bbox[3])/2:.1f}")
                            # 下标：x 在求和符号下方偏右，y 中心在求和符号中心下方
                            if other.bbox[0] > s.bbox[0] - 5 and other.bbox[2] < s.bbox[2] + 15:
                                other_cy = (other.bbox[1] + other.bbox[3]) / 2
                                s_cy = (s.bbox[1] + s.bbox[3]) / 2
                                if other_cy > s_cy:
                                    sub_spans.append(other)
                                    print(f"[sum]   sub candidate: {other.text}, x0={other.bbox[0]:.1f}, x1={other.bbox[2]:.1f}, cy={other_cy:.1f}")
                            # 上标：x 在求和符号上方偏右，y 中心在求和符号中心上方
                            if other.bbox[0] > s.bbox[0] - 5 and other.bbox[2] < s.bbox[2] + 15:
                                other_cy = (other.bbox[1] + other.bbox[3]) / 2
                                s_cy = (s.bbox[1] + s.bbox[3]) / 2
                                if other_cy < s_cy:
                                    sup_spans.append(other)
                    # 组合成 \sum_{...}^{...}
                    latex_cmd = VectorPdfTranslator._cmsy_to_latex(s.text, s.font_name)
                    sub_text = ''.join(t.text for t in sorted(sub_spans, key=lambda t: t.bbox[0]))
                    sup_text = ''.join(t.text for t in sorted(sup_spans, key=lambda t: t.bbox[0]))
                    if sub_text:
                        latex_cmd += '_{' + sub_text + '}'
                    if sup_text:
                        latex_cmd += '^{' + sup_text + '}'
                    print(f"[sum] sum bbox: {s.bbox}, sum cy: {(s.bbox[1]+s.bbox[3])/2}")
                    print(f"[sum] found sum: {latex_cmd}, sub_spans: {[s.text for s in sub_spans]}")
                    line_text += latex_cmd
                    cur_math += latex_cmd
                    for t in sub_spans + sup_spans:
                        processed.add(id(t))
                    processed.add(id(s))
                    continue
                if id(s) in processed:
                    continue
                line_text += s.text  # span text 自带空格
                if s.is_math:
                    cur_math += VectorPdfTranslator._cmsy_to_latex(s.text, s.font_name)
                else:
                    flush_math()
                is_bold = bool(s.flags & 16)
                if is_bold and s.text.strip() and s.size < 16 and not s.is_math:
                    blk.bold_terms.append(s.text.strip())
                # 识别缩写：带点的短词（如 r.v. i.i.d. p.m.f.）
                import re
                if re.match(r'^[a-zA-Z]\.[a-zA-Z.]*$', s.text.strip()):
                    blk.abbrev_symbols.append(s.text.strip())
                # 收集上下标字符
                if s.is_sup and s.text.strip():
                    blk.sup_symbols.append(s.text.strip())
                if s.is_sub and s.text.strip():
                    blk.sub_symbols.append(s.text.strip())
            flush_math()
            if line_text.strip():
                parts.append(line_text.strip())
        return " ".join(parts)

    # ---------- CMSY 字体字符 → LaTeX 命令 ----------
    _cmsy_map = {
        '1': r'\sum',
        '2': r'\prod',
        '3': r'\coprod',
        '4': r'\int',
        '5': r'\oint',
        '6': r'\bigcup',
        '7': r'\bigcap',
        '8': r'\bigoplus',
        '9': r'\bigotimes',
        '0': r'\bigodot',
    }
    @classmethod
    def _cmsy_to_latex(cls, text: str, font_name: str) -> str:
        """CMSY 字体的特殊字符映射成 LaTeX 命令"""
        if 'CMSY' not in font_name:
            return text
        result = ''
        for ch in text:
            if ch in cls._cmsy_map:
                result += cls._cmsy_map[ch]
            else:
                result += ch
        return result

    @classmethod
    def _join_block_text_with_sum(cls, lines: List[List[Span]]) -> str:
        """拼接文本，自动识别求和符号的上下标，组合成 \\sum_{...} 格式"""
        parts = []
        for line in lines:
            line_text = ''
            # 先找这行的求和符号 span
            sum_spans = [s for s in line if s.font_name.startswith('CMSY') and s.text in ('1', '2', '4')]
            for s in line:
                # 如果是求和符号，找到它的上下标
                if s in sum_spans:
                    # 找下标：y 在求和符号下方、x 范围重叠的小字号 span
                    sub_spans = []
                    sup_spans = []
                    for other in line:
                        if other is s:
                            continue
                        # 下标：y 在求和符号下方
                        if other.bbox[1] > s.bbox[3] - 5 and other.bbox[1] < s.bbox[3] + 20:
                            # x 范围重叠
                            if other.bbox[0] < s.bbox[2] and other.bbox[2] > s.bbox[0]:
                                sub_spans.append(other)
                        # 上标：y 在求和符号上方
                        if other.bbox[3] < s.bbox[1] + 5 and other.bbox[3] > s.bbox[1] - 20:
                            if other.bbox[0] < s.bbox[2] and other.bbox[2] > s.bbox[0]:
                                sup_spans.append(other)
                    # 组合成 \sum_{...}^{...}
                    latex_cmd = cls._cmsy_to_latex(s.text, s.font_name)
                    sub_text = ''.join(t.text for t in sorted(sub_spans, key=lambda t: t.bbox[0]))
                    sup_text = ''.join(t.text for t in sorted(sup_spans, key=lambda t: t.bbox[0]))
                    if sub_text:
                        latex_cmd += '_{' + sub_text + '}'
                    if sup_text:
                        latex_cmd += '^{' + sup_text + '}'
                    line_text += latex_cmd
                    # 标记上下标 span 已处理，后面不再输出
                    for t in sub_spans + sup_spans:
                        t._processed = True
                elif getattr(s, '_processed', False):
                    continue
                else:
                    line_text += cls._cmsy_to_latex(s.text, s.font_name)
            if line_text.strip():
                parts.append(line_text.strip())
        return ' '.join(parts)

    # ---------- LaTeX 公式解析：$...$ 块 → tokens 带 sup/sub flag ----------
    @staticmethod
    def _parse_latex(text: str) -> List[Tuple[str, int]]:
        """解析 $...$ LaTeX 块，返回 tokens: (text, flags)
        flags: bit1=math(斜体), bit2=sup(上标), bit3=sub(下标)
        """
        import re as _re
        tokens: List[Tuple[str, int]] = []
        # 先按 $$...$$ 或 $...$ 或 \(...\) 拆成普通文本和公式块
        parts = _re.split(r'(\$\$.*?\$\$|\$[^$]+\$|\\\(.*?\\\))', text)
        for part in parts:
            if not part:
                continue
            if part.startswith('$$') and part.endswith('$$'):
                inner = part[2:-2]
            elif part.startswith('$') and part.endswith('$'):
                inner = part[1:-1]
            elif part.startswith('\\(') and part.endswith('\\)'):
                inner = part[2:-2]  # 去掉 \( 和 \)
            else:
                tokens.append((part, 0))
                continue
            # 去掉 \ldots \sum 等命令，保留符号
            inner = inner.replace(r'\ldots', '...')
            inner = inner.replace(r'\sum', 'Σ')
            inner = inner.replace(r'\prod', 'Π')
            inner = inner.replace(r'\infty', '∞')
            inner = inner.replace(r'\times', '×')
            inner = inner.replace(r'\alpha', 'α')
            inner = inner.replace(r'\beta', 'β')
            inner = inner.replace(r'\gamma', 'γ')
            inner = inner.replace(r'\delta', 'δ')
            inner = inner.replace(r'\pi', 'π')
            inner = inner.replace(r'\theta', 'θ')
            inner = inner.replace(r'\lambda', 'λ')
            inner = inner.replace(r'\mu', 'μ')
            inner = inner.replace(r'\sigma', 'σ')
            inner = inner.replace(r'\phi', 'φ')
            inner = inner.replace(r'\psi', 'ψ')
            inner = inner.replace(r'\omega', 'ω')
            inner = inner.replace(r'\Delta', 'Δ')
            inner = inner.replace(r'\Phi', 'Φ')
            inner = inner.replace(r'\Psi', 'Ψ')
            inner = inner.replace(r'\Omega', 'Ω')
            inner = inner.replace(r'\in', '∈')
            inner = inner.replace(r'\forall', '∀')
            inner = inner.replace(r'\exists', '∃')
            inner = inner.replace(r'\neq', '≠')
            inner = inner.replace(r'\leq', '≤')
            inner = inner.replace(r'\geq', '≥')
            inner = inner.replace(r'\approx', '≈')
            inner = inner.replace(r'\pm', '±')
            inner = inner.replace(r'\div', '÷')
            # 解析下标 _ 和上标 ^
            cur = ''
            cur_flags = 2  # math
            i = 0
            while i < len(inner):
                ch = inner[i]
                if ch == '_' or ch == '^':
                    # 先把前面的普通文本输出
                    if cur:
                        tokens.append((cur, cur_flags))
                        cur = ''
                    # 取下标/上标内容：单个字符或 {..} 块
                    if i + 1 < len(inner) and inner[i+1] == '{':
                        j = inner.index('}', i+1)
                        sub = inner[i+2:j]
                        i = j
                    else:
                        sub = inner[i+1] if i+1 < len(inner) else ''
                        i += 1
                    flag = 4 if ch == '^' else 8  # bit2=sup, bit3=sub
                    tokens.append((sub, 2 | flag))  # math + sup/sub
                    cur_flags = 2  # 重置为普通 math
                else:
                    cur += ch
                i += 1
            if cur:
                tokens.append((cur, cur_flags))
        return tokens

    # ---------- 富文本 token 化：公式符号斜体 + 粗体术语标记 ----------
    def _tokenize_rich(self, text: str, bold_terms: List[str],
                       math_symbols: List[str],
                       abbrev_symbols: List[str] = None,
                       sup_symbols: List[str] = None,
                       sub_symbols: List[str] = None) -> List[Tuple[str, int]]:
        # flags: bit0=bold, bit1=math(斜体公式), bit2=sup(上标), bit3=sub(下标)
        # 先解析 LaTeX $...$ 块，生成带 math/sup/sub flag 的 tokens
        if self._render_math:
            tokens = self._parse_latex(text)
        else:
            # 关 render_math 时，识别 \(...\) 公式块，标记为 math（渲染时用 matplotlib）
            tokens = []
            import re as _re_math
            parts = _re_math.split(r'(\\\([^\\]+\\\))', text)
            for part in parts:
                if not part:
                    continue
                if part.startswith('\\(') and part.endswith('\\)'):
                    inner = part[2:-2]  # 去掉 \( 和 \)
                    tokens.append((inner, 2))  # math flag
                else:
                    tokens.append((part, 0))
        # 合并 math 和 abbrev，一起标记斜体
        all_symbols = list(math_symbols) + list(abbrev_symbols or [])
        # 1) 在译文中搜索公式/缩写符号，标记 bit1（斜体）
        #    按长度降序，避免短符号先匹配吃掉长符号
        seen = set()
        for sym in sorted(set(all_symbols), key=len, reverse=True):
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
        # 2) 标记上标（bit2）和下标（bit3）
        #    只匹配单字符数字/字母，避免误匹配
        for sym in sorted(set(sup_symbols or []), key=len, reverse=True):
            if not sym or len(sym) > 2:
                continue
            new_tokens: List[Tuple[str, int]] = []
            for t, fl in tokens:
                if fl & 1 or fl & 2 or fl & 4 or fl & 8:
                    new_tokens.append((t, fl)); continue
                pos = t.find(sym)
                if pos < 0:
                    new_tokens.append((t, fl)); continue
                if pos > 0:
                    new_tokens.append((t[:pos], fl))
                new_tokens.append((sym, fl | 4))  # bit2 = sup
                rest = t[pos + len(sym):]
                if rest:
                    new_tokens.append((rest, fl))
            tokens = new_tokens
        for sym in sorted(set(sub_symbols or []), key=len, reverse=True):
            if not sym or len(sym) > 2:
                continue
            new_tokens: List[Tuple[str, int]] = []
            for t, fl in tokens:
                if fl & 1 or fl & 2 or fl & 4 or fl & 8:
                    new_tokens.append((t, fl)); continue
                pos = t.find(sym)
                if pos < 0:
                    new_tokens.append((t, fl)); continue
                if pos > 0:
                    new_tokens.append((t[:pos], fl))
                new_tokens.append((sym, fl | 8))  # bit3 = sub
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
    _greek_chars = set('Σ∞αβγδπθλμσφψωΔΦΨΩ×÷±∈∀∃')
    _fm_symbol = None  # 缓存 Segoe UI Symbol 字体
    def _get_fm_symbol(self):
        if self._fm_symbol is None:
            self._fm_symbol = fitz.Font(fontfile=r"C:\Windows\Fonts\seguihis.ttf")
        return self._fm_symbol
    def _char_width(self, ch: str, flags: int, fontsize: float) -> float:
        bold = bool(flags & 1)
        math = bool(flags & 2)
        if ch in self._greek_chars:
            fm = self._get_fm_symbol()
            return fm.text_length(ch, fontsize=fontsize)
        elif _is_cjk(ch):
            fm = self._fm_cn_b if bold else self._fm_cn
        else:
            if math:
                fm = self._fm_en_i  # 斜体英文字体
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
             max_width: float, n_lines: int, base_size: float,
             single_line: bool = False
             ) -> Tuple[float, List[List[Tuple[str, int]]]]:
        # 先试原字号，不行再缩放；下限是原字号的 40%
        floor = max(5.0, base_size * 0.4)
        size = base_size
        while size > floor:
            wrapped = self._wrap_rich(tokens, max_width, size)
            if single_line:
                if len(wrapped) == 1:
                    return size, wrapped
            else:
                if len(wrapped) <= n_lines * 1.5:
                    return size, wrapped
            size -= 0.5
        wrapped = self._wrap_rich(tokens, max_width, floor)
        return floor, wrapped

    # ---------- 颜色 ----------
    @staticmethod
    def _rgb(c: int) -> Tuple[float, float, float]:
        return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

    # ---------- 段落绘制 ----------
    def _seg_width(self, seg: str, flags: int, fs: float) -> float:
        math = bool(flags & 2)
        if math:
            # math 公式用 matplotlib 渲染计算宽度
            _, orig_w, orig_h = self._render_math_to_pdf(seg, fs)
            if orig_h > 0:
                scale = fs / orig_h
                return orig_w * scale
            # fallback：用字体计算
        # 中文字符用中文字体，英文字符用英文字体（和渲染一致）
        total = 0.0
        for ch in seg:
            if _is_cjk(ch):
                total += self._char_width_cjk(ch, flags, fs)
            else:
                total += self._char_width(ch, flags, fs)
        return total

    def _char_width_cjk(self, ch: str, flags: int, fontsize: float) -> float:
        bold = bool(flags & 1)
        fm = self._fm_cn_b if bold else self._fm_cn
        return fm.text_length(ch, fontsize=fontsize)

    # ---------- LaTeX 公式渲染成 PNG ----------
    @staticmethod
    def _render_math_to_pdf(latex: str, fontsize: float = 12.0) -> tuple:
        """把 LaTeX 公式渲染成 PDF 矢量 bytes，返回 (pdf_bytes, width, height)"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import io
            # 创建一个临时 figure，只放公式
            fig = plt.figure(figsize=(0.01, 0.01))
            fig.text(0, 0, f'${latex}$', fontsize=fontsize)
            buf = io.BytesIO()
            fig.savefig(buf, format='pdf', bbox_inches='tight', pad_inches=0.02,
                        transparent=True)
            plt.close(fig)
            buf.seek(0)
            pdf_bytes = buf.read()
            # 获取尺寸（用 PyMuPDF 打开 PDF）
            import fitz as _fitz
            doc = _fitz.open("pdf", pdf_bytes)
            rect = doc[0].rect
            doc.close()
            return (pdf_bytes, rect.width, rect.height)
        except Exception as e:
            print(f"[math render error] {e}")
            return (None, 0, 0)

    def _draw_seg(self, page, x: float, y: float, seg: str,
                  flags: int, fs: float, color, rot: int) -> None:
        if not seg:
            return
        bold = bool(flags & 1)
        math = bool(flags & 2)
        is_sup = bool(flags & 4)
        is_sub = bool(flags & 8)
        is_latex = bool(flags & 16)  # 整个公式用 matplotlib 渲染成 PNG
        actual_fs = fs * 0.6 if (is_sup or is_sub) else fs
        actual_y = y - fs * 0.35 if is_sup else (y + fs * 0.2 if is_sub else y)
        # 按中英文拆段：中文用中文字体，英文用英文字体
        import re as _re_split
        parts = _re_split.findall(r'([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+|[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+)', seg)
        cur_x = x
        for part in parts:
            if not part:
                continue
            has_cjk = any(_is_cjk(ch) for ch in part)
            if bold:
                if has_cjk:
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs, fontname="F0",
                                     fontfile=BOLD_CN_FONT, color=color)
                else:
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs, fontname="hebo",
                                     color=color)
            elif math:
                # 所有公式都用 LaTeX 排版引擎（matplotlib mathtext）渲染成 PDF 矢量图形
                latex_str = seg
                pdf_bytes, orig_w, orig_h = self._render_math_to_pdf(latex_str, actual_fs)
                if pdf_bytes:
                    # 按当前字号缩放：高度按字号
                    scale = actual_fs / orig_h if orig_h > 0 else 1.0
                    new_w = orig_w * scale
                    new_h = orig_h * scale
                    # 公式 PDF 的基线在底部（y=0），对齐到文字基线 actual_y
                    rect = fitz.Rect(cur_x, actual_y - new_h,
                                     cur_x + new_w, actual_y)
                    page.show_pdf_page(rect, fitz.open("pdf", pdf_bytes), 0)
                    cur_x += new_w
                    continue
                # fallback：渲染失败时用字体渲染
                # 希腊字母和特殊符号用 Segoe UI Symbol 字体渲染
                greek_chars = 'Σ∞αβγδπθλμσφψωΔΦΨΩ×÷±∈∀∃'
                has_greek = any(c in greek_chars for c in part)
                if has_greek:
                    font_path = r"C:\Windows\Fonts\seguisym.ttf"  # Segoe UI Symbol
                    page.insert_font(fontname="seguisym", fontfile=font_path)
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs,
                                     fontname="seguisym", color=color)
                else:
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs,
                                     fontname="heit", color=color)
            else:
                if has_cjk:
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs,
                                     fontname=self.font_out, color=color)
                else:
                    page.insert_text((cur_x, actual_y), part, fontsize=actual_fs,
                                     fontname="helv", color=color)
            cur_x += self._seg_width(part, flags, actual_fs)

    # ---------- 单页 ----------
    def _detect_layout(self, page: fitz.Page) -> List[fitz.Rect]:
        """用 DocLayout-YOLO 检测页面版面，返回障碍物 bbox 列表（figure/table 等）"""
        if not self._layout_model:
            return []
        # 渲染页面成图片
        pix = page.get_pixmap(dpi=150)
        img_path = os.path.join(os.path.dirname(__file__), "_tmp_layout.png")
        pix.save(img_path)
        obstacles = []
        try:
            results = self._layout_model.predict(img_path, conf=0.3)
            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    # DocLayout-YOLO 类别: 0=text, 1=title, 2=figure, 3=table, 4=figure_caption, 5=table_caption
                    # 障碍物：figure, table
                    if cls in (2, 3):
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        # 从图片坐标转 PDF 坐标（dpi=150）
                        scale = 72.0 / 150.0
                        obstacles.append(fitz.Rect(x1 * scale, y1 * scale,
                                                   x2 * scale, y2 * scale))
        except Exception as e:
            print(f"[layout-ai] 检测失败: {e}")
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)
        return obstacles

    def translate_page(self, page: fitz.Page) -> int:
        rot = 0
        # 版面 AI 检测：拿到障碍物列表
        self._layout_obstacles = self._detect_layout(page) if self._use_layout_ai else []
        self._page_width = page.rect.width
        raw_blocks = self._collect_blocks(page)
        blocks = self._merge_blocks(raw_blocks)
        if not blocks:
            return 0

        originals_raw = [self._join_block_text(b) for b in blocks]
        # 提取编号前缀（1. 2. ① ② 等不翻译）
        import re
        prefixes = []
        originals = []
        for t in originals_raw:
            # 匹配 "1. " "2) " "3、" "① " "② " 等开头
            m = re.match(r'^(\d+[.\)、:]?\s*|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*|[•·]\s*)', t)
            if m:
                prefixes.append(m.group(1))
                originals.append(t[m.end():])
            else:
                prefixes.append("")
                originals.append(t)
        # 扫描全文：找出所有括号缩写（如 (r.v.)），建哈希表
        import re as _re
        abbrev_set = set()
        for t in originals_raw:
            # 只匹配短的、带点的学术缩写（如 (r.v.) (i.i.d.)）
            for m in _re.finditer(r'\([a-zA-Z]+\.[a-zA-Z.]*\)', t):
                if len(m.group(0)) <= 15:
                    abbrev_set.add(m.group(0))
        # 这些缩写直接保留不翻译：送翻译前替换成占位符
        abbrev_map = {}
        for i, ab in enumerate(abbrev_set):
            ph = f"[[ABBR{i}]]"
            abbrev_map[ph] = ab
        # 关 render_math 时，公式也直接保留不翻译：送翻译前替换成占位符
        math_map = {}
        math_images = {}  # ph → (png_bytes, orig_w, orig_h)
        if not self._render_math:
            math_set = set()
            for blk in blocks:
                for ms in blk.math_symbols:
                    if ms and len(ms) <= 20:  # 只保留短公式
                        math_set.add(ms)
            for i, ms in enumerate(math_set):
                ph = f"[[MATH{i}]]"
                math_map[ph] = ms
            # 把原文公式 span 渲染成 PNG（图片级平移）
            self._math_images = {}
            for blk in blocks:
                for line in blk.lines:
                    for s in line:
                        if s.is_math and s.text.strip() in math_set:
                            # 渲染这个 span 区域成 PNG
                            try:
                                clip = fitz.Rect(s.bbox)
                                pix = page.get_pixmap(clip=clip, dpi=300)
                                png_bytes = pix.tobytes("png")
                                # key 用占位符，渲染时匹配
                                ms = s.text.strip()
                                ph = f"[[MATH{list(math_set).index(ms)}]]"
                                self._math_images[ph] = (png_bytes, s.bbox[2] - s.bbox[0], s.bbox[3] - s.bbox[1])
                            except Exception:
                                pass
        def _apply_abbr(text):
            for ph, ab in abbrev_map.items():
                text = text.replace(ab, ph)
            for ph, ms in math_map.items():
                text = text.replace(ms, ph)
            return text
        def _restore_abbr(text):
            # 翻译 API 可能在占位符中间加空格，模糊匹配
            import re as _re2
            for ph, ab in abbrev_map.items():
                # 把 [[ABBR0]] 变成 [[\s*ABBR\s*0\s*]] 模糊匹配
                pat = _re2.escape(ph).replace(r'\[\[', r'\[\[\s*').replace(r'\]\]', r'\s*\]\]')
                text = _re2.sub(pat, ab, text)
            # 公式占位符保留，渲染时用 PNG 替换
            for ph, ms in math_map.items():
                pat = _re2.escape(ph).replace(r'\[\[', r'\[\[\s*').replace(r'\]\]', r'\s*\]\]')
                text = _re2.sub(pat, ph, text)
            return text
        originals = [_apply_abbr(t) for t in originals]
        translated = self._cached_translate(originals)
        # 翻译后：占位符换回原文
        translated = [_restore_abbr(t) for t in translated]
        # 清理 markdown 残留：去掉 ** ` _ 等多余符号
        import re as _re3
        translated = [_re3.sub(r'\*\*|`', '', t) for t in translated]
        # 清理 LaTeX 命令（保留 $$...$$ 包裹，让 _parse_latex 识别）
        translated = [t.replace('\\ldots', '...') for t in translated]
        translated = [t.replace('\\times', '×') for t in translated]
        translated = [t.replace('\\alpha', 'α') for t in translated]
        translated = [t.replace('\\beta', 'β') for t in translated]
        translated = [t.replace('\\gamma', 'γ') for t in translated]
        # 清理 \text{...} 命令，只保留内容
        import re as _re_text
        translated = [_re_text.sub(r'\\text\{([^}]*)\}', r'\1', t) for t in translated]
        # 去掉孤立的下划线（不是数字/字母中间的）
        translated = [_re3.sub(r'(?<![a-zA-Z0-9])_(?![a-zA-Z0-9])', '', t) for t in translated]
        # 合并连续单字符之间的多余空格（URL/数字被拆成单字符 span）
        def _collapse_spaces(t):
            prev = None
            while prev != t:
                prev = t
                # 单字符 + 空格 + 单字符 → 去掉空格（包括 : / . 等）
                t = _re3.sub(r'(\S) (?=\S(?: |$))', r'\1', t)
            return t
        translated = [_collapse_spaces(t) for t in translated]
        # 清理中文之间的多余空格（qwen 经常在公式和中文之间加空格）
        def _clean_cjk_spaces(t):
            # 中文字符 + 空格 + 中文字符 → 去掉空格
            t = _re3.sub(r'([\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', r'\1', t)
            # 中文 + 空格 + \( → 去掉空格
            t = _re3.sub(r'([\u4e00-\u9fff])\s+(?=\\\()', r'\1', t)
            # \) + 空格 + 中文 → 去掉空格
            t = _re3.sub(r'(\\\))\s+(?=[\u4e00-\u9fff])', r'\1', t)
            return t
        translated = [_clean_cjk_spaces(t) for t in translated]
        # 清理：去掉连续空格，保留正常的词间空格
        translated = [_re.sub(r' {2,}', ' ', t).strip() for t in translated]
        # 把编号前缀拼回译文
        translated = [p + t for p, t in zip(prefixes, translated)]

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
            tokens = self._tokenize_rich(new_text, blk.bold_terms, blk.math_symbols,
                                         blk.abbrev_symbols, blk.sup_symbols, blk.sub_symbols)
            if blk.is_all_bold:
                tokens = [(t, fl | 1) for t, fl in tokens]
            if not tokens:
                continue
            x0, y0, x1, y1 = blk.bbox
            max_w = x1 - x0  # 原文宽度，译文尽可能撑满
            n_orig = len(blk.line_baselines)
            single_line = (n_orig == 1)  # 单行 block（标题）不换行
            fit_size, wrapped = self._fit(tokens, max_w, n_orig, blk.main_size,
                                          single_line=single_line)
            color = self._rgb(blk.main_color)
            # 判断是否居中：block 中心在页面中心 ±5%，且宽度 < 70% 页面宽
            page_cx = self._page_width / 2
            blk_cx = (x0 + x1) / 2
            blk_w = x1 - x0
            is_centered = (abs(blk_cx - page_cx) < self._page_width * 0.05
                           and blk_w < self._page_width * 0.7)
            for i, line_tokens in enumerate(wrapped):
                # 行距按译文字号算，不用原文 baseline（英文行距太密，中文会重叠）
                y = blk.line_baselines[0] + i * fit_size * 1.4
                if is_centered:
                    # 居中：计算这一行总宽度，从中间开始
                    line_w = sum(self._seg_width(t, fl, fit_size) for t, fl in line_tokens)
                    x = page_cx - line_w / 2
                else:
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
    ap = argparse.ArgumentParser(description="PDF 段落翻译 v0.3")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--to", dest="dst_lang", default="zh")
    ap.add_argument("--engine", choices=["mock", "tencent", "qwen"], default="mock")
    ap.add_argument("--no-cache", action="store_true", help="禁用翻译缓存")
    ap.add_argument("--layout-ai", action="store_true", help="启用 DocLayout-YOLO 版面检测")
    ap.add_argument("--no-render-math", action="store_true", help="不重新渲染公式，保留原文公式")
    args = ap.parse_args(argv)

    if args.engine == "tencent":
        fn = TencentTranslator("en", args.dst_lang).translate_batch
    elif args.engine == "qwen":
        fn = QwenTranslator("en", args.dst_lang).translate_batch
    else:
        fn = MockTranslator().translate_batch
    tr = VectorPdfTranslator(
        fn, target_lang=args.dst_lang,
        use_cache=not args.no_cache,
        use_layout_ai=args.layout_ai,
        render_math=not args.no_render_math,
    )
    tr.run(args.src, args.dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
