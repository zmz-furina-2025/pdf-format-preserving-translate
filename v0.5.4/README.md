# v0.5.4 — 分块翻译 + qwen 公式保留

在 v0.5.3 基础上，加了分块翻译、qwen prompt 优化、公式保留。

## 核心改动

1. **分块翻译**：按占位符位置切段，每段单独翻译，再拼接。避免翻译 API 破坏占位符
2. **qwen prompt 优化**：明确说保留公式和变量，不翻译
3. **公式保留**：qwen 输出里公式原样保留，不重新渲染

## 跑

```bash
pip install pymupdf gradio requests
python demo_v0.5.4.py input.pdf output.pdf --engine qwen --no-render-math
```

可选参数：
- `--no-cache`：禁用翻译缓存
- `--layout-ai`：启用 DocLayout-YOLO 版面检测
- `--no-render-math`：不重新渲染公式，保留原文公式文字
- `--engine tencent` / `--engine qwen`

## 文件说明

- `demo_v0.5.4.py` — v0.5.4 主引擎
- `app.py` — Gradio 网页界面
- `Formula.modelfile` — Formula 模型配置（基于 qwen2.5vl:7b）
- `doclayout_yolo_docstructbench_imgsz1024.onnx` — DocLayout-YOLO 模型

## 当前状态

- 腾讯翻译：占位符总被破坏，公式渲染效果差
- qwen 翻译：prompt 里明确说保留公式，公式原样保留，翻译质量好
- 推荐用 qwen 翻译（需先装 Ollama + `ollama pull qwen2.5:latest`）
