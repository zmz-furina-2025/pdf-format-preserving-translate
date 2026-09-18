# PDF 排版保留翻译工具

核心差异化：**排版还原质量**——多栏、粗体、字号层级、矢量色块、图片背景都不丢。

## 版本

| 版本 | 内容 | Tag |
|---|---|---|
| v0.1 | 纯文字矢量 PDF：段落合并、粗体、翻译 API、基线对齐 | `v0.1` |
| v0.2 | v0.1 + 深色矢量块 / 图片背景保留（不挖白洞） | `v0.2` |
| v0.3 | v0.2 + 翻译缓存、编号前缀保留、缩写识别、qwen 本地引擎 | `v0.3` |
| v0.4 | v0.3 + 上下标正确渲染、DocLayout-YOLO 接入段落合并 | `v0.4` |
| v0.5 | v0.4 + LaTeX 公式解析渲染、中文空格清理、公式渲染开关 | `v0.5` |
| v0.5.1 | v0.5 + 段落合并修复、排序修复、文本框宽度修复 | `v0.5.1` |
| v0.5.2 | v0.5.1 + CMSY 字体字符 → Unicode 符号映射（Σ Π ∫） | `v0.5.2` |

## 快速开始

### 网页版（推荐）

双击根目录 `start.bat`，自动打开浏览器 http://127.0.0.1:7860。

### 命令行

```bash
cd src
python demo_v0.5.1.1.py input.pdf output.pdf --engine qwen
```

可选参数：
- `--no-cache`：禁用翻译缓存（默认开启）
- `--layout-ai`：启用 DocLayout-YOLO 版面检测（默认关）
- `--no-render-math`：不重新渲染公式（默认开，解析 LaTeX 重新渲染）
- `--engine qwen`：用本地 Ollama qwen 模型（需先装 ollama + `ollama pull qwen2.5:latest`）

## 翻译引擎配置

### 1. 云端翻译 API（云端，快）

1. 去云服务商控制台注册并创建 API 密钥（腾讯云 / 阿里云 / 百度等）
2. 开通「机器翻译」服务（新用户有免费额度）
3. 把密钥填到项目根目录的 `.env` 文件：
   ```
   TENCENT_SECRET_ID=你的SecretId
   TENCENT_SECRET_KEY=你的SecretKey
   TENCENT_REGION=ap-shanghai
   ```

### 2. 本地 qwen 小模型（离线，学术质量好）

1. 安装 [Ollama](https://ollama.com/)
2. 拉取模型（推荐 7B，约 4GB）：
   ```bash
   ollama pull qwen2.5:7b
   ```
3. 启动 Ollama 服务（默认端口 11434）
4. 确保 GPU 驱动已装，模型会自动用 GPU 加速

## 当前版本：v0.5.2

基于 v0.5.1，新增：
- CMSY 字体字符 → Unicode 符号映射（`1` → Σ, `2` → Π, `4` → ∫）
- 求和符号 Σ 正确显示（之前显示为 `1`）

## 技术栈

- PDF 解析：PyMuPDF
- 翻译：云端翻译 API（HTTP + TC3 签名直调）/ 本地 Ollama qwen
- 粗体：雅黑粗体 + Helvetica Bold 按字符选字体
- 背景保留：redaction `images=NONE, graphics=NONE`
- 缓存：JSON 文件 MD5 key
- 版面检测：DocLayout-YOLO（可选）
