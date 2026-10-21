# 项目记忆（smartops-agent）

## 一、LLM 后端配置（以 .env 为准，禁止输出密钥）
- 本项目 LLM 后端为 **DeepSeek（经第三方中转）**，配置来源：`smartops-agent/.env`。
- 关键配置项（占位示例，仅用于说明，不输出真实密钥）：
  - `ARK_API_KEY=<真实 Key 在 .env 里，禁止在对话或代码中输出、打印、硬编码>`
  - `ARK_BASE_URL=https://api.deepseek.com/v1`（OpenAI 兼容格式，不使用 Anthropic 格式）
  - `ARK_MODEL=deepseek-chat`
- `src/core/llm.py` 使用 `openai.OpenAI(api_key, base_url)` 客户端，不使用 `ChatAnthropic`。
- Key 读取统一由 `src/core/config.py` 的 `os.getenv("ARK_API_KEY")` 完成。
  - 严禁 echo Key、写日志、写文档明文显示。
- 不改 `.env`（除非你明确要求）。
- 若新增环境变量，需同步更新 `.env.example` 并使用占位符（如 `your_key_here`）。

## 二、Windows CMD 环境变量规范（必须遵守）
- **致命坑**：`set VAR=1 &&` 中 `=` 后有空格会把值带尾随空格，导致 Python 读取异常（如 `PYTHONUTF8`）。
- **正确写法**（优先）：
  ```bat
  set "HF_HUB_OFFLINE=1" && set "PYTHONUTF8=1" && set "PYTHONIOENCODING=utf-8"
  ```
- 也可分行写：每行一个 `set`，并保证无尾随空格。
- 本项目标准模板：
  ```bat
  set "HF_HUB_OFFLINE=1" && set "PYTHONUTF8=1" && set "PYTHONIOENCODING=utf-8" && .venv\Scripts\python.exe <命令>
  ```

### 运行方式（推荐）
- 项目已提供 `run.bat`：优先使用
  - `run.bat main.py`
  - `run.bat -m src.evaluation.evaluate`

## 三、其他项目约定
- 必须使用项目环境：`.venv\Scripts\python.exe`（不要用全局 `python`）。
- 默认启用：`HF_HUB_OFFLINE=1`（国内网络场景下避免 HF 离线检查超时）。
- 依赖约束：`transformers` 为 4.x（例如 4.57.6），`tokenizers` 为 0.22.2；避免升级到 `transformers 5.x`，避免 `tokenizers 0.23.1` 与 `sentence_transformers` 兼容问题。
- ChromaDB collection 名称要求：3-512 字符，只能 `[a-zA-Z0-9._-]`，首尾字母数字（如 `kb` 不合法）。
- 中文乱码时设置 `PYTHONUTF8=1`。
- 本项目使用第三方中转 API，密钥安全优先：任何密钥操作先确认来源，禁止提交明文（git 或记忆）。
