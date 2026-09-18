"""
app.py — Gradio 界面版 PDF 翻译 demo
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

# 动态加载 demo_v0.2.1.py（文件名带点，不能直接 import）
_spec = importlib.util.spec_from_file_location(
    "engine", os.path.join(os.path.dirname(__file__), "demo_v0.2.1.py")
)
_engine_mod = importlib.util.module_from_spec(_spec)
sys.modules["engine"] = _engine_mod  # dataclass 需要在 sys.modules 里找到模块
_spec.loader.exec_module(_engine_mod)

MockTranslator = _engine_mod.MockTranslator
TencentTranslator = _engine_mod.TencentTranslator
VectorPdfTranslator = _engine_mod.VectorPdfTranslator


def translate_pdf(pdf_file, engine: str):
    if pdf_file is None:
        return None, "请先上传 PDF"
    src = pdf_file.name
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    dst = tmp.name
    tmp.close()
    try:
        if engine == "tencent":
            fn = TencentTranslator("en", "zh").translate_batch
        else:
            fn = MockTranslator().translate_batch
        VectorPdfTranslator(fn, target_lang="zh").run(src, dst)
        return dst, "翻译完成"
    except Exception as e:
        return None, f"出错：{e}"


with gr.Blocks(title="PDF 排版保留翻译") as demo:
    gr.Markdown("# PDF 排版保留翻译\n矢量型 PDF，保住多栏 / 粗体 / 色块 / 图片背景。")
    with gr.Row():
        pdf_in = gr.File(label="上传 PDF", file_types=[".pdf"])
        engine = gr.Radio(["mock", "tencent"], value="mock",
                          label="翻译引擎", info="mock=伪翻译不花钱，tencent=腾讯云真实翻译")
    btn = gr.Button("开始翻译", variant="primary")
    status = gr.Textbox(label="状态")
    pdf_out = gr.File(label="译文 PDF")
    btn.click(translate_pdf, inputs=[pdf_in, engine], outputs=[pdf_out, status])

if __name__ == "__main__":
    demo.launch()
