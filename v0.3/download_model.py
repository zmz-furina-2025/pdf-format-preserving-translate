import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="wybxc/DocLayout-YOLO-DocStructBench-onnx",
    filename="doclayout_yolo_docstructbench_imgsz1024.onnx",
    local_dir=".",
)
print(f"Model downloaded to: {path}")
