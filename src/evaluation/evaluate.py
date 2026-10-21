"""
evaluation/evaluate.py - 自动化评估 V2（4项指标 + 版本对比 + A/B测试）

运行: cd smartops-agent && HF_HUB_OFFLINE=1 PYTHONUTF8=1 .venv/Scripts/python.exe -m src.evaluation.evaluate
"""
import os, time, json, re, yaml, asyncio
from datetime import datetime
os.environ['HF_HUB_OFFLINE'] = '1'
from src.rag.embedding import get_embedding_function, get_client
from src.orchestration.graph import build_graph
from src.core.synonym_dict import normalize

# === 建知识库（对应测试集 case_id: d0~d5） ===
DEPT_MAP = {"功率调度":"控制器部门","储能":"储能部门","通信":"通信硬件组","电网协议":"电网协议组","逆变器":"逆变器硬件组"}
docs = [
    # 功率调度
    ("光伏逆变器输出功率低于设定值,dispatch_power()限值逻辑", "功率调度"),
    ("功率限值触发:电网调度指令、需量管理、限电保护", "功率调度"),
    ("多功能同时开启:功能互斥逻辑冲突,功率异常波动", "功率调度"),
    ("充电桩占用电量:功率重分配策略异常,光伏出力受影响", "功率调度"),
    ("无功补偿控制:参数配置偏差,实际输出与设定不符", "功率调度"),
    # 储能
    ("储能电池SOC跳变,BMS通信状态检查,SOC校准", "储能"),
    ("BMS SOC估算算法漂移:开路电压法校准参数失效", "储能"),
    ("电池温度保护降额:充电功率自动降低,温度传感器正常", "储能"),
    ("储能簇间不均衡:均衡策略未生效,簇间SOC偏差超10%", "储能"),
    # 通信
    ("Modbus通信超时,寄存器地址、波特率、终端电阻", "通信"),
    ("485总线干扰:时断时续,终端电阻已加但仍有反射", "通信"),
    ("Modbus TCP协议栈异常:ping正常但读写超时", "通信"),
    ("通信网关缓存溢出:多设备掉线恢复后数据丢失", "通信"),
    # 电网协议
    ("IEC104协议不通,TCP2404端口,ASDU地址配置", "电网协议"),
    ("遥测召唤标志位:104遥测不上报,链路状态正常", "电网协议"),
    ("总召唤分帧间隔:耗时超3分钟,数据量正常", "电网协议"),
    # 逆变器
    ("逆变器过温停机,IGBT温度超阈值,降额保护", "逆变器"),
    ("绝缘阻抗检测异常:开机报绝缘低,天气晴朗", "逆变器"),
    ("MPPT跟踪异常:直流侧电压波动,组件无遮挡", "逆变器"),
]
client = get_client()
try: client.delete_collection("eval_kb_v2")
except: pass
kb = client.create_collection("eval_kb_v2", embedding_function=get_embedding_function())
kb.add(documents=[d for d, _ in docs],
       metadatas=[{"id": f"d{i}", "domain": dom, "dept": DEPT_MAP[dom]} for i, (_, dom) in enumerate(docs)],
       ids=[f"d{i}" for i in range(len(docs))])

app = build_graph(kb)

# === 加载测试集 ===
_test_set_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_set.yaml")
with open(_test_set_path, encoding='utf-8') as f:
    test_set = yaml.safe_load(f)

# === 评估函数 ===
def run_eval(use_synonym=False, prompt_version=None):
    """跑一轮评估, 返回指标 dict"""
    n = len(test_set)
    route_ok = recall_ok = fields_total = 0
    times = []
    details = []

    for case in test_set:
        query = normalize(case["description"]) if use_synonym else case["description"]
        t0 = time.time()
        try:
            r = asyncio.run(app.ainvoke({"query": query, "parsed": {}, "dept": "", "route_conf": 0,
                                         "retrieved": [], "search_score": 0, "confidence": 0, "result": ""}))
        except Exception as e:
            # 单条失败不中断整轮评估, 记为错例
            print(f"  [case异常] {case['description'][:30]}... -> {e}")
            times.append(time.time() - t0)
            details.append({
                "query": case["description"][:30],
                "pred_dept": "ERROR",
                "true_dept": case["true_dept"],
                "dept_ok": False,
                "recall_ok": False,
                "elapsed": round(time.time() - t0, 1),
            })
            continue
        elapsed = time.time() - t0
        times.append(elapsed)

        # ① 路由准确率
        dept_ok = r["dept"] == case["true_dept"]
        if dept_ok: route_ok += 1

        # ② Top3 召回
        retrieved_ids = [d[0] for d in r.get("retrieved", [])][:3]
        case_ok = case["true_case_id"] in retrieved_ids
        if case_ok: recall_ok += 1

        # ④ 字段完整率
        m = re.search(r'\{.*\}', r["result"], re.DOTALL)
        if m:
            ticket = json.loads(m.group())
            fields_total += sum(1 for k, v in ticket.items() if v or k == "related_cases") / 7  # related_cases空也算填

        details.append({
            "query": case["description"][:30],
            "pred_dept": r["dept"],
            "true_dept": case["true_dept"],
            "dept_ok": dept_ok,
            "recall_ok": case_ok,
            "elapsed": round(elapsed, 1),
        })

    return {
        "route_accuracy": round(route_ok / n * 100, 1),
        "recall_top3": round(recall_ok / n * 100, 1),
        "avg_time": round(sum(times) / n, 1),
        "field_completeness": round(fields_total / n * 100, 1),
        "details": details,
    }

# === 主评估 ===
print("=" * 60)
print("V2 评估 — 基线 (无同义词)")
print("=" * 60)
baseline = run_eval(use_synonym=False)

for d in baseline["details"]:
    flag = "✅" if d["dept_ok"] else "❌"
    print(f"  {d['query']}... -> {d['pred_dept']}(真:{d['true_dept']}) {flag}")

print(f"\n=== 评估结果 V2 基线 (n={len(test_set)}) ===")
print(f"① 路由准确率: {baseline['route_accuracy']}%   (V2目标≥78%)")
print(f"② Top3召回:   {baseline['recall_top3']}%       (V2目标≥88%)")
print(f"③ 平均耗时:   {baseline['avg_time']}s        (V2目标<120s)")
print(f"④ 字段完整率: {baseline['field_completeness']}%       (V2目标≥95%)")

# === 同义词对比 ===
print(f"\n{'='*60}")
print("V2 评估 — 启用同义词")
print("=" * 60)
synonym_result = run_eval(use_synonym=True)

for d in synonym_result["details"]:
    flag = "✅" if d["dept_ok"] else "❌"
    print(f"  {d['query']}... -> {d['pred_dept']}(真:{d['true_dept']}) {flag}")

print(f"\n=== 评估结果 同义词版 (n={len(test_set)}) ===")
print(f"① 路由准确率: {synonym_result['route_accuracy']}%")
print(f"② Top3召回:   {synonym_result['recall_top3']}%")
print(f"③ 平均耗时:   {synonym_result['avg_time']}s")
print(f"④ 字段完整率: {synonym_result['field_completeness']}%")

# === 版本对比摘要 ===
print(f"\n{'='*60}")
print("版本对比摘要")
print("=" * 60)
print(f"{'指标':<16} {'基线':>8} {'+同义词':>8} {'变化':>8} {'V2目标':>8}")
print("-" * 56)
for key, label, target in [
    ("route_accuracy", "路由准确率%", 78),
    ("recall_top3", "Top3召回%", 88),
    ("avg_time", "平均耗时s", 120),
    ("field_completeness", "字段完整率%", 95),
]:
    b = baseline[key]
    s = synonym_result[key]
    delta = f"+{s-b:.1f}" if s >= b else f"{s-b:.1f}"
    print(f"{label:<16} {b:>7.1f} {s:>7.1f} {delta:>8} {target:>7}")

# === 保存结果 ===
result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_results.yaml")
record = {
    "timestamp": datetime.now().isoformat(),
    "test_count": len(test_set),
    "baseline": {k: v for k, v in baseline.items() if k != "details"},
    "with_synonym": {k: v for k, v in synonym_result.items() if k != "details"},
    "misrouted": [d for d in baseline["details"] if not d["dept_ok"]],
}
with open(result_path, "w", encoding="utf-8") as f:
    yaml.dump(record, f, allow_unicode=True, default_flow_style=False)
print(f"\n评估结果已保存至: {result_path}")
