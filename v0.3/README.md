# v0.3 — 缓存 + 缩写 + qwen + layout-ai 开关

在 v0.2 基础上，加了翻译缓存、缩写保留、本地 qwen 引擎、DocLayout-YOLO 版面检测开关。

## 核心改动

1. **翻译缓存**：同一个句子不重复调用 API，JSON 文件存缓存，断了重跑不花钱
2. **编号前缀保留**：`1. xxx`、`2) xxx`、`① xxx` 等编号不参与翻译，只翻译后面的内容
3. **缩写保留**：`r.v.`、`i.i.d.` 这种学术缩写按文本模式识别，翻译后斜体保留
4. **本地 qwen 引擎**：Ollama 跑 qwen2.5:latest，学术翻译质量更好，不花钱
5. **DocLayout-YOLO 开关**：`--layout-ai` 参数开启，AI 版面检测作为段落合并障碍物

## 跑

```bash
pip install pymupdf gradio requests
python demo_v0.3.1.py input.pdf output.pdf --engine qwen
```

可选参数：
- `--no-cache`：禁用翻译缓存
- `--layout-ai`：启用 DocLayout-YOLO 版面检测
- `--engine tencent`：用腾讯云翻译（需 .env 凭证）
- `--engine qwen`：用本地 Ollama qwen 模型（需先装 ollama + `ollama pull qwen2.5:latest`）

## 文件说明

- `demo_v0.3.1.py` — v0.3 主引擎
- `app.py` — Gradio 网页界面
- `doclayout_yolo_docstructbench_imgsz1024.onnx` — DocLayout-YOLO 模型（75MB）
- `download_model.py` — 下载模型脚本

## 成果文件

- `out_v03.pdf` — 基础翻译效果
- `out_v03_abbr.pdf` — 缩写保留效果
- `out_v03_layout.pdf` — DocLayout-YOLO 开启效果
