"""
core/config.py - 核心配置(所有模块 import 这里, 不散落)
从 .env 读敏感信息, 常量集中管理
"""
import os
from dotenv import load_dotenv

load_dotenv()  # 读 .env

# === LLM(火山方舟 coding 端点, 与 Claude Code 同)==
ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding")
ARK_MODEL = os.getenv("ARK_MODEL", "glm-5.2")
LLM_MAX_TOKENS = 2048

# === Embedding(BGE-large-zh, 本地 GPU)===
EMBEDDING_MODEL = "BAAI/bge-large-zh"
# RTX 3050 4G 显存紧张/被其他程序占用时可临时切 CPU: set EMBEDDING_DEVICE=cpu
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")

# === ChromaDB ===
CHROMA_PATH = "chroma_db"  # 持久化路径(空则内存)
HF_ENDPOINT = "https://hf-mirror.com"  # HF 镜像
os.environ.setdefault("HF_ENDPOINT", HF_ENDPOINT)

# === 路由 ===
DEPTS = ["控制器部门", "逆变器硬件组", "储能部门", "通信硬件组", "电网协议组", "充电桩组", "电网侧(非本部门)", "不确定"]

# === 置信度 ===
CONFIDENCE_THRESHOLD = 0.7   # ≥0.7 走工单, <0.7 走专家
ROUTE_WEIGHT = 0.6           # 路由置信度权重
SEARCH_WEIGHT = 0.4          # 检索匹配度权重

# === 解析 Agent ===
MANDATORY_FIELDS = ["devices", "phenomenon", "firmware_version"]
# 3选2：先保证核心字段可用，避免整流程因字段不足中断
FIELD_MIN_FILLED = 2
MAX_ASK_ROUNDS = 2           # 追问最多2轮
