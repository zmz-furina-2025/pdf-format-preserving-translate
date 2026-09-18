# v0.5 — LaTeX 公式解析渲染 + 中文空格清理

在 v0.4 基础上，加了 LaTeX 公式解析渲染、公式渲染开关、中文空格清理、希腊字母修复。

## 核心改动

1. **LaTeX 公式解析**：qwen 输出 `\(...\)` LaTeX 格式，解析下标 `_`、上标 `^`
2. **公式渲染开关**：
   - 开（默认）：解析 LaTeX 重新渲染，下标小号低位置，上标小号高位置
   - 关（`--no-render-math`）：公式内容用斜体英文字体渲染，清理 LaTeX 标记
3. **中文空格清理**：清理 qwen 输出里中文之间的多余空格
4. **希腊字母修复**：Σ α β γ 用中文字体渲染，避免 helv 缺字符
5. **markdown 残留清理**：去掉 `**`、`` ` ``、孤立 `_`、`\text{...}` 等

## 跑

```bash
pip install pymupdf gradio requests
python demo_v0.5.1.py input.pdf output.pdf --engine qwen
```

可选参数：
- `--no-cache`：禁用翻译缓存
- `--layout-ai`：启用 DocLayout-YOLO 版面检测
- `--no-render-math`：不重新渲染公式，保留原文公式文字
- `--engine tencent` / `--engine qwen` / `--engine mock`

## 文件说明

- `demo_v0.5.1.py` — v0.5 主引擎
- `app.py` — Gradio 网页界面（带"重新渲染公式"勾选框）
- `doclayout_yolo_docstructbench_imgsz1024.onnx` — DocLayout-YOLO 模型

## 成果文件

- `out_v05_final.pdf` — LaTeX 公式解析效果
- `out_v05_spaces.pdf` — 中文空格清理效果
- `out_v05_keepmath2.pdf` — 不重新渲染公式效果
