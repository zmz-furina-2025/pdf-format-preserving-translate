# v0.2 — 支持矢量色块 / 图片背景

在 v0.1 基础上，**文字压在深色矢量块或图片上时不再挖白洞**。

## 核心改动

redaction 不再涂白，而是只删文字对象：

```python
page.apply_redactions(
    images=fitz.PDF_REDACT_IMAGE_NONE,    # 保留图片
    graphics=fitz.PDF_REDACT_LINE_ART_NONE,  # 保留矢量色块/线条
)
```

矢量型 PDF 的文字和背景本来就是独立对象，删文字不影响背景——不需要 Inpainting。

## 跑

```bash
pip install pymupdf Pillow
python make_sample.py        # 纯文字双栏
python make_sample_bg.py     # 带深色块 + 渐变图片
python demo.py sample_bg.pdf out_bg.pdf --engine tencent
```

## 成果文件

- `out_v5.pdf` / `preview_v5.png`：纯文字双栏效果
- `out_bg.pdf` / `preview_bg.png`：深色块白字 + 渐变图片黑字效果

## 和 v0.1 的差别

| | v0.1 | v0.2 |
|---|---|---|
| 白底纯文字 | ✅ | ✅ |
| 深色矢量块背景 | ❌ 挖白洞 | ✅ 保留 |
| 图片背景 | ❌ 挖白洞 | ✅ 保留 |
