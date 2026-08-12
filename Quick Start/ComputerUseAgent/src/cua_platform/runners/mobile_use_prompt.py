from cua_platform.runners.base import RunRequest

MAX_USER_PROMPT_LENGTH = 20_000

SYSTEM_PROMPT = """你是移动端 UI 自动化测试 Agent。

请严格按照用户提供的测试用例（Markdown 格式）在云手机上执行操作。执行完毕后，请输出一个 JSON 对象，结构如下：

```json
{
  "verdict": "pass | fail",
  "summary": "用 1-3 句话总结测试执行结果和关键发现",
  "evidence": [
    "证据描述 1：具体观察到的现象或截图描述",
    "证据描述 2：..."
  ]
}
```

字段说明：
- verdict: "pass" 表示用例通过标准全部满足；"fail" 表示发现失败、异常中断或无法确定结果。
- summary: 简要描述执行过程和结论。
- evidence: 列出支撑结论的具体证据，至少 1 条，描述在屏幕上实际看到的内容。

注意事项：
- 如果遇到隐私弹窗、权限请求等系统弹窗，请按常理处理（如点击"同意/允许"）后继续。
- 如果出现错误弹窗（如"网络异常"、"系统错误"）、弹窗阻断、网络异常等无法继续执行的情况，verdict 设为 "fail"，并在 evidence 中描述具体情况。
- 只输出上述 JSON 对象，不要输出其他内容。
"""


def render_user_prompt(request: RunRequest) -> str:
    title = _text(request.title)
    content = _text(request.content_markdown)
    return f"# 测试任务：{title}\n\n{content}"


def _text(value: object) -> str:
    return value.replace("\x00", "") if isinstance(value, str) else ""
