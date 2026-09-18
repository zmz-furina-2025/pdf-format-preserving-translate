@echo off
cd /d "%~dp0src"
echo === PDF Translator v0.5.1.1 ===

where python >nul 2>nul || (echo [ERROR] Python not found. Install Python 3.10+ && pause && exit /b 1)

python -c "import gradio, fitz" 2>nul
if errorlevel 1 (
    echo [INFO] First run, installing dependencies...
    python -m pip install --quiet gradio pymupdf requests
)

echo [INFO] Starting... opening browser.
start "" http://127.0.0.1:7860
python app.py

pause
