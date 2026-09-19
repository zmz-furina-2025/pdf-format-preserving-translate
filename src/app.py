"""
app.py — Gradio 界面版 PDF 翻译 v0.5.4
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

# 动态加载 demo_v0.5.4.py（文件名带点，不能直接 import）
_spec = importlib.util.spec_from_file_location(
    "engine", os.path.join(os.path.dirname(__file__), "demo_v0.5.4.py")
)
_engine_mod = importlib.util.module_from_spec(_spec)
sys.modules["engine"] = _engine_mod
_spec.loader.exec_module(_engine_mod)

MockTranslator = _engine_mod.MockTranslator
TencentTranslator = _engine_mod.TencentTranslator
QwenTranslator = _engine_mod.QwenTranslator
VectorPdfTranslator = _engine_mod.VectorPdfTranslator


def translate_pdf(pdf_file, engine: str, use_cache: bool, use_layout_ai: bool, render_math: bool,
                  secret_id: str, secret_key: str,
                  qwen_host: str, qwen_model: str):
    if pdf_file is None:
        return None, "请先上传 PDF"
    print(f"[DEBUG] engine={engine!r}, qwen_model={qwen_model!r}")
    src = pdf_file.name
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    dst = tmp.name
    tmp.close()
    try:
        if engine == "tencent":
            if not secret_id or not secret_key:
                return None, "请先填 SecretId 和 SecretKey"
            fn = TencentTranslator("en", "zh", secret_id=secret_id, secret_key=secret_key).translate_batch
        elif engine == "qwen":
            fn = QwenTranslator("en", "zh", host=qwen_host, model=qwen_model).translate_batch
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


# ---- 引擎选择时显示/隐藏配置 ----
def on_engine_change(engine: str):
    if engine == "tencent":
        return gr.update(visible=True), gr.update(visible=False)
    elif engine == "qwen":
        return gr.update(visible=False), gr.update(visible=True)
    else:
        return gr.update(visible=False), gr.update(visible=False)


with gr.Blocks(title="PDF 排版保留翻译 v0.5.4") as demo:
    gr.Markdown("# PDF 排版保留翻译 v0.5.4\n矢量型 PDF，保住多栏 / 粗体 / 色块 / 图片背景。")
    with gr.Row():
        pdf_in = gr.File(label="上传 PDF", file_types=[".pdf"])
        engine = gr.Radio(
            [("Mock（伪翻译不花钱）", "mock"), ("云端翻译 API（快）", "tencent"), ("本地 qwen（离线高质量）", "qwen")],
            value="mock",
            label="翻译引擎",
        )

    # ---- 云端 API 配置（选云端翻译 API 时显示）----
    with gr.Group(visible=False) as tencent_group:
        gr.Markdown("### 云端翻译 API 配置")
        secret_id = gr.Textbox(label="SecretId", placeholder="腾讯云 SecretId")
        secret_key = gr.Textbox(label="SecretKey", placeholder="腾讯云 SecretKey", type="password")
        gr.Markdown(
            """
            **怎么拿密钥**：
            1. 去 [腾讯云控制台](https://console.cloud.tencent.com/cam/capi) 注册
            2. 开通「机器翻译」服务（新用户有免费额度）
            3. 把 SecretId 和 SecretKey 填到上面
            """
        )

    # ---- qwen 配置（选 qwen 时显示）----
    with gr.Group(visible=False) as qwen_group:
        gr.Markdown("### 本地 qwen 小模型配置")
        qwen_host = gr.Textbox(label="Ollama 地址", value="http://localhost:11434")
        qwen_model = gr.Textbox(label="模型名", value="qwen2.5:latest")
        gr.Markdown(
            """
            **怎么装 qwen**：
            1. 安装 [Ollama](https://ollama.com/)
            2. 打开终端，跑：`ollama pull qwen2.5:7b`（约 4GB）
            3. 启动 Ollama 服务（默认端口 11434）
            4. 确保 GPU 驱动已装，模型会自动用 GPU 加速
            """
        )

    engine.change(on_engine_change, inputs=[engine], outputs=[tencent_group, qwen_group])

    with gr.Row():
        use_cache = gr.Checkbox(value=True, label="翻译缓存", info="同一个句子不重复花钱")
        use_layout_ai = gr.Checkbox(value=False, label="DocLayout-YOLO", info="AI 版面检测（默认关）")
        render_math = gr.Checkbox(value=True, label="重新渲染公式", info="关=保留原文公式位置，开=解析 LaTeX 重新渲染")

    btn = gr.Button("开始翻译", variant="primary")
    status = gr.Textbox(label="状态")
    pdf_out = gr.File(label="译文 PDF")
    btn.click(translate_pdf,
              inputs=[pdf_in, engine, use_cache, use_layout_ai, render_math,
                      secret_id, secret_key, qwen_host, qwen_model],
              outputs=[pdf_out, status])

if __name__ == "__main__":
    demo.launch()
