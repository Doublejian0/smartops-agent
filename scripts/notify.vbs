' SmartOps 任务完成提醒弹窗
' 用法: wscript scripts/notify.vbs "提醒内容"
' 原理: Windows自带的VBScript, 调用MsgBox弹模态框, 带提示音和任务栏闪烁
Set args = WScript.Arguments
msg = "任务完成"
If args.Count > 0 Then msg = args(0)
MsgBox msg, vbInformation, "SmartOps 提醒"
