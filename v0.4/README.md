# v0.4 — 上下标 + 居中对齐 + CJK/EN 分字体

在 v0.3 基础上，加了上下标正确渲染、居中对齐、中英文分字体渲染、颜色放宽、排序 bug 修复。

## 核心改动

1. **上下标正确渲染**：识别 PDF 里的上标/下标 span，翻译后用小号字高低错位渲染
2. **居中对齐**：block 中心在页面中间 ±5% 且宽度 < 70% 页面宽时，渲染时计算译文宽度居中放
3. **CJK/EN 分字体渲染**：中文用 china-s，英文用 helv，避免 china-s 字体里英文字符全角导致间距过大
4. **颜色判断放宽**：公式 span（CMMI 字体）颜色偏色，导致同一段被拆成两个 block。放宽到 RGB 差 30 就算同色
5. **行距修复**：之前用原文英文行距排中文导致两行重叠，改成按译文字号 1.4 倍排
6. **封面页排序 bug 修复**：block 按 x0 聚类排序后，October 14（下面）排在 Wen Dingzhu（上面）前面，gap 变负数被误判 close=True 错误合并。修复：gap < 0 时不合并
7. **标题不换行**：单行 block（n_orig==1）强制 single_line 不换行，缩字号到一行能放下
8. **markdown 残留清理**：去掉 `**`、`` ` ``、孤立 `_` 等

## 跑

```bash
pip install pymupdf gradio requests
python demo_v0.4.1.py input.pdf output.pdf --engine qwen
```

可选参数：
- `--no-cache`：禁用翻译缓存
- `--layout-ai`：启用 DocLayout-YOLO 版面检测
- `--engine tencent` / `--engine qwen` / `--engine mock`

## 文件说明

- `demo_v0.4.1.py` — v0.4 主引擎
- `app.py` — Gradio 网页界面
- `doclayout_yolo_docstructbench_imgsz1024.onnx` — DocLayout-YOLO 模型

## 成果文件

- `out_v04_center.pdf` — 居中对齐效果
- `out_v04_split.pdf` — 中英文分字体效果
- `out_v04_spaces.pdf` — 空格清理效果
