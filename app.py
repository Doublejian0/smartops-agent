"""app.py - Gradio 前端 V2（结果高亮 / 来源标注 / 置信度展示 / 日志上传 / 反馈回写）

运行: cd smartops-agent && HF_HUB_OFFLINE=1 PYTHONUTF8=1 .venv/Scripts/python.exe app.py
"""
import os, json, html
os.environ['HF_HUB_OFFLINE'] = '1'

import gradio as gr
from src.rag.embedding import get_embedding_function, get_client
from src.orchestration.graph import build_graph
from src.mcp.tools.log_analyzer import log_analyzer

# === 初始化知识库 + 编排图 ===
DEPT_MAP = {"功率调度":"控制器部门","储能":"储能部门","通信":"通信硬件组","电网协议":"电网协议组","逆变器":"逆变器硬件组"}
_docs = [
    ("光伏逆变器输出功率低于设定值,dispatch_power()限值逻辑", "功率调度"),
    ("功率限值触发:电网调度指令、需量管理、限电保护", "功率调度"),
    ("储能电池SOC跳变,BMS通信状态检查,SOC校准", "储能"),
    ("Modbus通信超时,寄存器地址、波特率、终端电阻", "通信"),
    ("IEC104协议不通,TCP2404端口,ASDU地址配置", "电网协议"),
    ("逆变器过温停机,IGBT温度超阈值,降额保护", "逆变器"),
]
client = get_client()
try: client.delete_collection("gradio_kb")
except: pass
kb = client.create_collection("gradio_kb", embedding_function=get_embedding_function())
kb.add(documents=[d for d, _ in _docs],
       metadatas=[{"id": f"d{i}", "domain": dom, "dept": DEPT_MAP[dom]} for i, (_, dom) in enumerate(_docs)],
       ids=[f"d{i}" for i in range(len(_docs))])
app_graph = build_graph(kb)

# === 样式常量 ===
CONFIDENCE_COLORS = {
    "high": "#22c55e",    # ≥0.70 绿色
    "medium": "#f59e0b",  # 0.40-0.69 橙色
    "low": "#ef4444",     # <0.40 红色
}

def conf_level(score):
    if score >= 0.70: return "high"
    if score >= 0.40: return "medium"
    return "low"

def conf_bar_html(score, label=""):
    """置信度进度条"""
    pct = int(score * 100)
    color = CONFIDENCE_COLORS[conf_level(score)]
    return f"""
    <div style="margin:4px 0">
      <span style="font-size:13px;color:#888">{label}</span>
      <div style="background:#333;border-radius:6px;height:18px;margin:2px 0">
        <div style="background:{color};width:{pct}%;height:100%;border-radius:6px;transition:width 0.5s"></div>
      </div>
      <span style="font-size:12px;color:#aaa">{pct}%</span>
    </div>"""

# === 核心处理函数 ===
async def diagnose(query: str, log_file=None):
    """主诊断入口"""
    if not query.strip():
        return "", "", "", "", "", "请输入故障描述"

    # 日志上传处理
    log_info = ""
    if log_file is not None:
        try:
            log_text = log_file.decode('utf-8') if isinstance(log_file, bytes) else str(log_file)
            parsed_log = log_analyzer(log_text[:5000])
            log_info = (
                f"📋 **日志解析结果**\n"
                f"- 错误码: {', '.join(parsed_log.get('error_codes', []) or ['无'])}\n"
                f"- 异常信息: {len(parsed_log.get('exceptions', []))} 处\n"
                f"- 涉及函数: {', '.join(parsed_log.get('functions', [])[:5] or ['无'])}\n"
                f"- 含调用栈: {'是' if parsed_log.get('has_stack_trace') else '否'}\n"
            )
            query = f"{query}\n[日志摘要] 错误码:{parsed_log.get('error_codes', [])}"
        except Exception as e:
            log_info = f"⚠️ 日志解析失败: {e}"

    # 执行诊断
    result = await app_graph.ainvoke({
        "query": query, "parsed": {}, "dept": "", "route_conf": 0,
        "retrieved": [], "search_score": 0, "confidence": 0, "result": ""
    })

    # --- V2 新增: 门卫拦截/追问的快捷展示(提前返回, 不走后续面板) ---
    gate_dept = result.get("dept", "")
    if gate_dept in ("拒绝", "待补全"):
        emoji, title, color = ("🚫", "查询被拦截", "#ef4444") if gate_dept == "拒绝" else ("🤔", "需要补充信息", "#f59e0b")
        gate_html = f"""
    <div style="font-family:monospace;padding:12px;background:#2a1a1a;border-radius:8px">
      <h3 style="margin:0 0 8px;color:{color}">{emoji} {title}</h3>
      <p style="color:#ddd;white-space:pre-wrap;font-size:15px">{html.escape(result.get('result', ''))}</p>
    </div>"""
        return (
            gate_html,
            "",
            result.get("result", ""),
            log_info if log_info else "（未上传日志）",
            "",
            f"诊断ID: {result.get('diagnosis_id', 'N/A')}",
        )

    # --- 面板 1: 路由信息 ---
    route_conf = result.get("route_conf", 0)
    confidence = result.get("confidence", 0)
    dept = result.get("dept", "未知")
    route_html = f"""
    <div style="font-family:monospace;padding:12px;background:#1a1a2e;border-radius:8px">
      <h3 style="margin:0 0 8px;color:#e0e0e0">🎯 路由判定</h3>
      <p style="font-size:18px;color:#fff"><b>{html.escape(dept)}</b></p>
      {conf_bar_html(route_conf, '路由置信度')}
      {conf_bar_html(confidence, '综合置信度')}
      <p style="font-size:12px;color:#666;margin-top:4px">
      综合置信度 = 路由{route_conf:.2f}×{0.6} + 检索{result.get('search_score',0):.2f}×{0.4}
      </p>
    </div>"""

    # --- 面板 2: 检索结果（来源标注）---
    retrieved = result.get("retrieved", [])
    search_rows = ""
    for i, (doc_id, doc_text, score) in enumerate(retrieved[:5]):
        doc_preview = html.escape(doc_text[:80]) + ("..." if len(doc_text) > 80 else "")
        search_rows += f"""
        <tr>
          <td style="color:#888;padding:4px 8px">#{i+1}</td>
          <td style="padding:4px 8px"><code style="color:#a78bfa">{html.escape(doc_id)}</code></td>
          <td style="padding:4px 8px;color:#ccc">{doc_preview}</td>
          <td style="padding:4px 8px;color:#f59e0b">{score:.3f}</td>
        </tr>"""
    search_html = f"""
    <div style="font-family:monospace;padding:12px;background:#1a1a2e;border-radius:8px;margin-top:8px">
      <h3 style="margin:0 0 8px;color:#e0e0e0">📚 检索结果（Top5，含来源标注）</h3>
      <table style="width:100%;font-size:13px;border-collapse:collapse">
        <tr style="color:#888;text-align:left">
          <th style="padding:4px 8px">#</th>
          <th style="padding:4px 8px">来源</th>
          <th style="padding:4px 8px">内容</th>
          <th style="padding:4px 8px">得分</th>
        </tr>
        {search_rows}
      </table>
    </div>"""

    # --- 面板 3: 诊断结果 ---
    result_text = result.get("result", "")
    # 尝试格式化 JSON
    try:
        ticket = json.loads(result_text)
        result_formatted = f"""```json
{json.dumps(ticket, ensure_ascii=False, indent=2)}
```"""
    except (json.JSONDecodeError, TypeError):
        result_formatted = result_text

    # --- 面板 4: Skill 推荐 ---
    from src.skills.matcher import skill_match
    skill, skill_score = skill_match(query, dept)
    skill_name = skill["name"] if skill else "无匹配"
    skill_steps = ""
    if skill:
        skill_steps = "<ol>" + "".join(f"<li>{html.escape(s)}</li>" for s in skill.get("steps", [])) + "</ol>"
    skill_html = f"""
    <div style="font-family:monospace;padding:12px;background:#1a1a2e;border-radius:8px;margin-top:8px">
      <h3 style="margin:0 0 8px;color:#e0e0e0">🔧 推荐排查 Skill: {html.escape(skill_name)} <span style="color:#f59e0b">({skill_score}分)</span></h3>
      {skill_steps}
    </div>"""

    return (
        route_html,
        search_html,
        result_formatted,
        log_info if log_info else "（未上传日志）",
        skill_html,
        f"诊断ID: {result.get('diagnosis_id', 'N/A')}",
    )

async def confirm_diagnosis(diag_id: str, corrected_dept: str, root_cause: str):
    """人工确认/修正后回写知识库"""
    if not diag_id or "N/A" in diag_id:
        return "⚠️ 无有效诊断ID, 请先执行诊断"

    # 通过 graph 的 feedback 节点回写
    result = await app_graph.ainvoke({
        "query": "", "parsed": {}, "dept": corrected_dept or "控制器部门",
        "route_conf": 0, "retrieved": [], "search_score": 0,
        "confidence": 0, "result": "",
        "diagnosis_id": diag_id.replace("诊断ID: ", ""),
        "feedback_confirmed": True,
        "feedback_dept": corrected_dept,
        "feedback_root_cause": root_cause,
    })
    return f"✅ 已回写知识库 | 归属: {corrected_dept} | 根因: {root_cause}"


# === Gradio UI ===
with gr.Blocks(title="SmartHEMS 智能运维诊断 V2", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🔍 SmartHEMS 智能运维故障诊断系统 V2

    输入故障描述，自动判定归属部门、检索历史案例、生成工单草稿、推荐排查 Skill。
    支持上传日志文件自动解析关键信息。
    """)

    with gr.Row():
        with gr.Column(scale=3):
            query_input = gr.Textbox(
                label="故障描述",
                placeholder="例如: 光伏逆变器输出功率15kW, 实测10kW, Modbus寄存器读值正常...",
                lines=3,
            )
            log_upload = gr.File(label="📎 上传日志文件（可选）", file_types=[".txt", ".log"])
            submit_btn = gr.Button("🚀 开始诊断", variant="primary", size="lg")

        with gr.Column(scale=2):
            route_output = gr.HTML(label="路由判定")
            skill_output = gr.HTML(label="Skill 推荐")

    with gr.Row():
        search_output = gr.HTML(label="检索结果")

    with gr.Row():
        result_output = gr.Markdown(label="诊断结果 / 工单草稿")

    with gr.Row():
        log_output = gr.Markdown(label="日志解析")

    # === 反馈回写区 ===
    gr.Markdown("---\n### ✏️ 人工确认与反馈回写")
    with gr.Row():
        diag_id_display = gr.Textbox(label="诊断ID", interactive=False, scale=1)
        corrected_dept = gr.Dropdown(
            label="修正归属部门",
            choices=["控制器部门", "逆变器硬件组", "储能部门", "通信硬件组", "电网协议组", "充电桩组", "电网侧(非本部门)", "不确定"],
            scale=1,
        )
        root_cause_input = gr.Textbox(label="补充根因（可选）", placeholder="如: dispatch_power限值逻辑异常", scale=2)
    confirm_btn = gr.Button("✅ 确认并回写知识库", variant="secondary")
    feedback_status = gr.Markdown("")

    submit_btn.click(
        fn=diagnose,
        inputs=[query_input, log_upload],
        outputs=[route_output, search_output, result_output, log_output, skill_output, diag_id_display],
    )

    confirm_btn.click(
        fn=confirm_diagnosis,
        inputs=[diag_id_display, corrected_dept, root_cause_input],
        outputs=[feedback_status],
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)
