# v0.5.3 — 图片级平移尝试 + Formula 模型调研

在 v0.5 基础上，尝试了图片级平移公式方案。

## 核心改动

1. **图片级平移尝试**：把原文公式 span 渲染成 PNG，平移到译文对应位置
2. **Formula 模型**：基于 qwen2.5vl:7b 的公式识别模型，识别准确率高

## 图片级平移方案（失败）

尝试了多种占位符方案：
- `[[MATH0]]` → 翻译 API 把 MATH 翻译成 PATH
- `§0§` → 翻译 API 把数字删掉
- `█` → 翻译 API 把 █ 翻译成 RST
- `{{{0}}}` → 翻译 API 把大括号改掉

**结论**：翻译 API 会破坏任何占位符，图片级平移方案走不通。

## Formula 模型（验证成功）

基于 qwen2.5vl:7b 创建了 Formula 模型：
- 识别准确率高（下标、大括号都对）
- 输出标准 LaTeX
- 8GB 显存跑得动

但接入引擎需要解决占位符问题，工程量大。

## 跑

```bash
pip install pymupdf gradio requests
python demo_v0.5.3.py input.pdf output.pdf --engine qwen
```

可选参数：
- `--no-cache`：禁用翻译缓存
- `--layout-ai`：启用 DocLayout-YOLO 版面检测
- `--no-render-math`：不重新渲染公式，保留原文公式文字
- `--engine tencent` / `--engine qwen`

## 文件说明

- `demo_v0.5.3.py` — v0.5.3 主引擎
- `app.py` — Gradio 网页界面
- `Formula.modelfile` — Formula 模型配置
- `doclayout_yolo_docstructbench_imgsz1024.onnx` — DocLayout-YOLO 模型

## 当前状态

图片级平移方案失败，回到 v0.5 的稳定方案（不重新渲染公式，保留原文文字）。
Formula 模型已验证可用，后续可接入。
