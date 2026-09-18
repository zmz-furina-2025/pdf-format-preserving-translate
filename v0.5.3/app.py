"""
app.py — Gradio 界面版 PDF 翻译 v0.5
拖入 PDF → 选引擎 → 出译文 PDF。

跑：
  python app.py
浏览器打开 http://127.0.0.1:7860
"""
import importlib.util
import os
import sys
import tempfile

import gradio as gr

# 动态加载 demo_v0.5.3.py（文件名带点，不能直接 import）
_spec = importlib.util.spec_from_file_location(
    "engine", os.path.join(os.path.dirname(__file__), "demo_v0.5.3.py")
)
_engine_mod = importlib.util.module_from_spec(_spec)
sys.modules["engine"] = _engine_mod
_spec.loader.exec_module(_engine_mod)

MockTranslator = _engine_mod.MockTranslator
TencentTranslator = _engine_mod.TencentTranslator
QwenTranslator = _engine_mod.QwenTranslator
VectorPdfTranslator = _engine_mod.VectorPdfTranslator


def translate_pdf(pdf_file, engine: str, use_cache: bool, use_layout_ai: bool, render_math: bool):
    if pdf_file is None:
        return None, "请先上传 PDF"
    src = pdf_file.name
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    dst = tmp.name
    tmp.close()
    try:
        if engine == "tencent":
            fn = TencentTranslator("en", "zh").translate_batch
        elif engine == "qwen":
            fn = QwenTranslator("en", "zh").translate_batch
        else:
            fn = MockTranslator().translate_batch
        tr = VectorPdfTranslator(
            fn, target_lang="zh",
            use_cache=use_cache,
            use_layout_ai=use_layout_ai,
            render_math=render_math,
        )
        tr.run(src, dst)
        return dst, "翻译完成"
    except Exception as e:
        return None, f"出错：{e}"


with gr.Blocks(title="PDF 排版保留翻译 v0.5") as demo:
    gr.Markdown("# PDF 排版保留翻译 v0.5\n矢量型 PDF，保住多栏 / 粗体 / 色块 / 图片背景。\n新增：LaTeX 公式解析渲染、中文空格清理。")
    with gr.Row():
        pdf_in = gr.File(label="上传 PDF", file_types=[".pdf"])
        engine = gr.Radio(["mock", "tencent", "qwen"], value="mock",
                          label="翻译引擎", info="mock=伪翻译不花钱，tencent=腾讯云，qwen=本地 Ollama")
    with gr.Row():
        use_cache = gr.Checkbox(value=True, label="翻译缓存", info="同一个句子不重复花钱")
        use_layout_ai = gr.Checkbox(value=False, label="DocLayout-YOLO", info="AI 版面检测（需另装模型，默认关）")
        render_math = gr.Checkbox(value=True, label="重新渲染公式", info="关=保留原文公式位置，开=解析 LaTeX 重新渲染")
    btn = gr.Button("开始翻译", variant="primary")
    status = gr.Textbox(label="状态")
    pdf_out = gr.File(label="译文 PDF")
    btn.click(translate_pdf, inputs=[pdf_in, engine, use_cache, use_layout_ai, render_math],
              outputs=[pdf_out, status])

if __name__ == "__main__":
    demo.launch()
