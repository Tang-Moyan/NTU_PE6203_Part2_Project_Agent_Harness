# Reviewer 实现与交接说明

负责人：曹晓晗

## 本轮文件

- `reviewer/llm_reviewer.py`：替换原文件，保留原 `MockReviewer`。
- `tests/test_reviewer.py`：保留原来的两个测试，补充 11 个 LLM Reviewer 离线测试。
- 本文：供组内交接及最终报告引用。

沿用已经完成的 `reviewer/prompt_templates.py`。不修改 `core/gate.py`、`policies/`、`reviewer/base.py`。
JSON 解析直接放在 `llm_reviewer.py` 中，不依赖此前单独编写的 `response_parser.py`；该旧文件可以保留，但当前实现不会调用它。

## 实现与分工要求对应

1. `review()` 首先调用原有 `sanitize_context()`。
2. 格式化已有 System/User Prompt，提供任务、历史、工具名称和原始工具参数。
3. 通过 OpenAI SDK 的 `client.chat.completions.create()` 调用兼容端点。
4. 严格解析 JSON：仅接受 `approved`（真正的布尔值）和非空字符串 `reason`。
5. 将 API 返回的总 token 用量写入 `ReviewerDecision.token_cost`；metadata 额外记录输入、输出 token。
6. API 错误、拒答、响应不完整、JSON 错误均不批准，并记录可区分的状态。
7. 返回 `ReviewerDecision`。审批预算由既有 Gate 管理，Reviewer 不修改预算、不执行工具。

## Prompt 设计思路

审核以用户授权、操作对象和参数范围为中心，不把所有读取一律视作安全，也不把所有删除一律视作危险。
检索内容、工具输出和引用文本不构成新的授权。模型应提供简短的判断理由，并返回可解析 JSON。
Prompt 的这些规则是设计目标；真实判断质量必须通过模型实测验证。

## 信息隔离的实现及边界

- 必须先调用已有脱敏函数；历史结构中的已知 Oracle 键再递归过滤。
- 不把 task_id、任意任务/工具 metadata、raw_call 送入 Prompt；历史消息只提取 role/content。
- 测试检查实际传给 API 客户端的 messages，而非仅检查脱敏函数返回值。
- 键过滤不能识别任意自然语言或未知字段中的隐藏答案。AgentDojo 上下文构建端仍必须只提供真实审核者可见的任务、消息和历史观察，不能把评测成功条件写入普通文本。
- 当前调用的参数必须忠实反映待审批操作，不能为了掩盖泄漏而随意删除业务参数。上下文构建端须确保这里也是实际 Agent 工具参数，而不是评测对象。
- 本实现不主动记录完整 Prompt、API Key 或异常原文；正式集成后还需抽样检查最终 Prompt 与运行日志。

## 失败和成本口径

| status | 含义 |
| --- | --- |
| parsed | 成功解析真实或测试客户端的回答，批准与否由 approved 表示 |
| parse_error | JSON 或字段类型不合规，同时记录 parse_error=true |
| api_error | 调用失败，例如超时、鉴权或接口错误 |
| model_refusal | 模型显式拒答 |
| response_error | 无候选回答、截断或过滤等异常结束 |
| configuration_error | 缺模型名称或 API Key，没有完成审核 |

非 parsed 状态不应当作模型正确识别危险操作的证据。评测组应单独统计技术失败。
API 未返回用量时，token_cost=0 只是兼容整数接口的占位，usage_available=false、total_tokens=null 表示成本未知。
本客户端禁用 SDK 自动重试，避免隐藏的多次调用。第三方服务内部的计费和重试仍需按该服务核实。

## 配置和运行

参数优先于环境变量。可设置：

- `REVIEWER_MODEL`：团队选定的准确模型 ID；必须设置。
- `REVIEWER_API_KEY`：所选平台的 Key；必须设置，除非离线测试注入 client。
- `REVIEWER_BASE_URL`：该平台的 OpenAI 兼容 API 基础地址。省略时由 SDK 使用 OpenAI 服务；使用其他平台必须填写其地址。

不得把 Key 写进代码或上传 GitHub。需要确认平台、模型及参数支持情况；部分模型不接受 temperature，可构造 `LLMSimulatedReviewer(temperature=None)` 省略此参数。
本实现通过 Prompt 要求严格 JSON，不强制发送供应商专属的结构化输出选项；不合规回答会按 parse_error 拒绝。

Colab 中保持工作目录为项目根目录，先运行离线检查：

```python
!python -m unittest tests.test_reviewer -v
!python -m unittest discover -s tests -v
```

确认真实 API 信息后，在单独的 Colab 单元配置（替换平台和模型占位文本）：

```python
import os
from getpass import getpass

os.environ["REVIEWER_MODEL"] = "团队确认的模型ID"
os.environ["REVIEWER_BASE_URL"] = "团队确认的API基础地址"
os.environ["REVIEWER_API_KEY"] = getpass("请输入API Key（隐藏输入）：")
```

再运行以下命令；这一步会发起真实请求，可能收费：

```python
!python scripts/smoke_reviewer.py --use-llm
```

原 smoke 脚本末尾可能仍打印旧的 Skeleton 提示，那是脚本中写死的文案，不代表当前实现。判断时查看实际 status、approved、reason 和 token 用量。
如果返回 configuration_error/api_error 等，先解决配置或连接问题，不可把默认拒绝误当作安全测试通过。

## 已验证与未验证

### Offline verification

- 全项目离线 unittest 测试已通过。
- Reviewer 测试覆盖批准/拒绝解析、无效 JSON、信息隔离、输入不变、
  Gate 预算联动、超时、拒答、截断、空响应、缺失用量和配置接线。
- MockReviewer 用于确定性离线测试和无 API 环境下的流水线验证。

### Real-model verification

The LLM Reviewer was connected to OpenRouter using the
`openai/gpt-4o-mini` model through an OpenAI-compatible Chat Completions API.

Initial live smoke test:

- Authorized log-reading call: approved as expected.
- Destructive `DROP DATABASE` call outside the user's scope: denied as expected.
- Result: 2/2 cases passed.
- Both responses returned `status=parsed` and real token-usage metadata.

Extended prompt self-test:

- 8 test cases covering authorized operations, destructive actions,
  sensitive-file access, explicit deletion authorization, scope violations,
  untrusted tool-output instructions, and ambiguous authorization.
- Result: 8/8 cases passed.
- Test expectations were stored outside the TaskContext and were not shown
  to the reviewer model.
- Detailed sanitized results are stored in
  `evaluation/results/reviewer_real_model_test_results.json`.

### Remaining limitations

- The current results are a targeted real-model prompt self-test, not the
  full AgentDojo benchmark evaluation.
- Results were obtained from one model and a limited test set, so they do
  not establish general performance across models or tasks.
- API availability, provider behavior and model versions may affect
  reproducibility.
- Formal evaluation should additionally report task completion,
  escalation load, failures and token costs across approval budgets.
