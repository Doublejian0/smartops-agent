# ============================================
# 智能运维故障诊断系统 - 容器化部署
# 构建: docker build -t smartops-agent .
# ============================================
FROM python:3.11-slim

WORKDIR /app

# 先只 COPY 依赖文件，利用 Docker 层缓存：代码改动不触发重装依赖
COPY requirements.txt .

# 装依赖（清华镜像加速；torch 装 CPU 版，容器内 embedding 走 CPU）
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目代码
COPY . .

# 环境变量：
#   HF_ENDPOINT       HuggingFace 镜像（下载 BGE 模型用）
#   HF_HUB_OFFLINE=0  首次启动允许联网下载模型（下载后由卷缓存，重启不再下）
#   EMBEDDING_DEVICE  CPU（容器默认无 GPU，避免 CUDA 报错）
#   PYTHONUTF8        中文编码
ENV HF_ENDPOINT=https://hf-mirror.com \
    HF_HUB_OFFLINE=0 \
    EMBEDDING_DEVICE=cpu \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8

# 暴露 FastAPI 端口
EXPOSE 8000

# 启动 FastAPI。
# 注意：用单 worker —— 多 worker 会重复加载 BGE 模型 + ChromaDB SQLite 并发冲突，
#       教学/演示场景单 worker 足够，生产高并发再配多进程 + 独立向量库服务。
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
