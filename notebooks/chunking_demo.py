"""
0.3 分块策略 Demo: 文档入库前怎么切
演示: 固定大小分块 + overlap重叠 的作用
(纯字符串操作, 不加载模型, 秒跑)

运行: smartops-agent/.venv/Scripts/python.exe notebooks/chunking_demo.py
"""

# 一段模拟的运维手册文本(实际是产品手册的某个章节)
doc = """功率调度模块负责协调光伏、储能、充电桩的功率分配。
当光伏输出功率低于设定值时,系统会检查调度策略是否干预。
调度策略包括削峰填谷、需量管理、备用电源模式。
如果调度策略未干预,再检查电网限电保护是否触发。
电网限电保护触发时,系统会自动降低输出以保护设备。
储能SOC低于20%时禁止放电,优先充电。
BMS通信异常时,储能充放电功能会自动锁定。"""

def split_by_size(text, chunk_size, overlap):
    """固定大小分块, 带 overlap 重叠
    步进 = chunk_size - overlap: 每次前进(块大小-重叠), 保证相邻块有 overlap 字符重叠
    """
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + chunk_size]
        chunks.append(chunk)
        next_start = start + chunk_size - overlap
        if next_start <= start:  # 防止死循环
            break
        start = next_start
    return chunks

print("=== 原文 ===")
print(doc)
print(f"(共 {len(doc)} 字符)\n")

# 演示1: 无 overlap, 句子可能被切断
print("=== 分块1: chunk_size=45, overlap=0(无重叠, 注意被切断的句子)===")
for i, c in enumerate(split_by_size(doc, 45, 0)):
    print(f"  块{i}: 「{c}」")

# 演示2: 有 overlap=15, 边界内容在相邻块重复出现
print("\n=== 分块2: chunk_size=45, overlap=15(重叠15字符, 边界信息不丢)===")
for i, c in enumerate(split_by_size(doc, 45, 15)):
    print(f"  块{i}: 「{c}」")

print("""
要点:
  1) chunk_size: 块大小。文档建议 512-1024 tokens(这里用字符简化演示原理)
  2) overlap: 相邻块重叠, 避免切断句子导致语义残缺
  3) 对比: 分块1把句子切两半(如"调度策略包括"和"削峰填谷..."分开);
           分块2重叠让边界内容在两块都有, 检索时更容易命中完整语义
  4) 实际项目按"天然结构"切(章节/案例/函数), 不机械按字数切""")
