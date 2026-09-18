# v0.1 — 纯文字矢量 PDF

只处理**白底纯文字**的矢量型 PDF。深色矢量块或图片背景上的文字会被涂白，挖出白洞。

## 跑

```bash
pip install pymupdf
python make_sample.py
python demo.py sample.pdf out.pdf                  # 伪翻译
python demo.py sample_v3.pdf out.pdf --engine tencent  # 真实翻译（需 .env）
```

## 能力

- PyMuPDF 提取 block/span，跨 block 合并段落
- 腾讯云 TMT 真实翻译（HTTP 签名直调）
- 粗体保留：整段粗体 block + 段落内术语对齐
- `span.origin[1]` 精确基线
- 字号自适应（译文超出原宽度就缩字号）
- 双栏、字号层级、灰色脚注保留
- 中文逐字换行 / 英文按词换行

## 局限

- **深色矢量块背景**：会挖白洞（v0.2 解决）
- **图片背景**：会挖白洞（v0.2 解决）
- **表格**：未识别单元格结构
- **跨页段落**：未处理
- **扫描型 PDF**：未处理
