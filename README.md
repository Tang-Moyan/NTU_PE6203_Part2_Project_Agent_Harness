# Agent Harness Approval Gate (AgentDojo)

AI Agent 工具调用审批网关系统（Three-way Approval Policy Gate）。

本系统用于在 AI Agent（如 AgentDojo 评测框架中的 Agent）调用外部工具（执行 Shell、调用 API、读写文件）时，提供一个介于“全人工审批（Full Human Review）”与“全自动放行（Full Auto-Execution）”之间的安全审批网关，在有限的人工审查预算 `k` 约束下，最大化安全任务完成率（Safe Task Completion Rate, TCR@k），并最小化人工干预负载（HITL Load）。

---

## 1. 核心架构设计

审批网关对每个工具调用进行三分类决策（Three-way Decision）：
1. **Auto-approve（自动放行）**：判定为安全且符合用户意图的操作，无需人工介入直接执行。
2. **Auto-deny（自动拦截）**：判定为明显不安全、越权或注入攻击的操作，自动予以阻断。
3. **Escalate（升级到人工）**：判定为模糊、高风险或破坏性操作，转交人类审查员（或 LLM 模拟审查员）进行裁决。

### 预算约束与退化机制（Degradation Mechanism）
- 每个任务分配固定的人工审查预算 `k`（每任务最大升级次数）。
- 当预算 `k > 0` 时，策略的 `Escalate` 请求会消耗 1 点预算并调用 Reviewer。
- **一旦预算 `k` 耗尽（`k = 0`），后续所有产生 `Escalate` 的决策将自动退化为 `Auto-deny` 并阻断工具执行**，防止未经确认的高危操作造成破坏。

---

## 2. 代码工程目录结构

```text
.
├── README.md                      # 项目文档与分工开发指南
├── requirements.txt               # 项目依赖声明
├── pyproject.toml                 # 构建配置与测试配置
├── main.py                        # 流程串联演示脚本 (Demo Entry)
├── scripts/                       # 组员一键自测 Smoke 脚本
│   ├── smoke_reviewer.py
│   ├── smoke_smart_policy.py
│   └── smoke_evaluation.py
├── team_guides/                   # 各角色任务指南（含验证命令）
│
├── core/                          # 核心底层框架（架构搭建）
│   ├── __init__.py
│   ├── models.py                  # 核心数据模型 (ToolCall, TaskContext, GateResult 等)
│   ├── budget.py                  # 预算跟踪器 (BudgetTracker, 约束与退化逻辑)
│   ├── base.py                    # 策略与审查员抽象基类 (BaseApprovalPolicy, BaseHumanReviewer)
│   └── gate.py                    # 核心审批网关 (ApprovalGate)
│
├── policies/                      # 审批策略模块
│   ├── __init__.py
│   ├── baselines/                 # 基线策略（基线策略开发）
│   │   ├── __init__.py
│   │   ├── full_approve.py        # Full-approve 基线（全自动放行，无防御）
│   │   ├── full_escalate.py       # Full-escalate 基线（全人工审查，耗尽即阻断）
│   │   └── rule_based.py          # 规则/启发式基线（只读放行、危险命令阻断）
│   └── smart/                     # 智能审批策略（智能策略开发）
│       ├── __init__.py
│       └── smart_policy.py        # 预算感知的确定性风险分类器（三分类已实现）
│
├── reviewer/                      # 模拟人工审查员模块（LLM 模拟审查员）
│   ├── __init__.py
│   ├── base.py                    # 审查员基类与 Oracle 信息隔离脱敏器
│   ├── prompt_templates.py        # 审查员 Prompt 模板 (已留空，待填充)
│   └── llm_reviewer.py            # LLM 模拟审查员实现与 MockReviewer
│
├── evaluation/                    # 评测与统计模块（评测与归因）
│   ├── __init__.py
│   ├── metrics.py                 # TCR@k、HITL Load、Token Cost 等评测指标模型
│   └── runner.py                  # TCR 曲线评测运行器框架 (已预留 TODO)
│
├── agentdojo_integration/         # AgentDojo 拦截适配层（架构搭建）
│   ├── __init__.py
│   └── adapter.py                 # AgentDojo 工具包装器与中间件拦截器
│
└── tests/                         # 自动化测试用例
    ├── __init__.py
    ├── test_models_and_budget.py  # 基础数据结构与预算逻辑单元测试
    ├── test_baselines.py          # 基线策略单元测试
    ├── test_reviewer.py           # 审查员与信息隔离测试
    ├── test_gate.py               # 网关三分类路由与退化机制测试
    ├── test_smart_policy.py       # 智能策略三分类、敏感数据与预算感知测试
    └── test_end_to_end.py         # 端到端闭环流程集成测试
```

---

## 3. 组员分工与代码落脚点指南

更详细的任务说明、修改位置与验收标准见 [`team_guides/`](./team_guides/) 目录。

| 负责组员 | 职责分工 | 核心开发文件 / 模块 | 详细指南 |
| :--- | :--- | :--- | :--- |
| **汤墨言** | 架构搭建与技术支持 | `core/`、`agentdojo_integration/`、`main.py` | [01_汤墨言_架构搭建与技术支持.md](./team_guides/01_汤墨言_架构搭建与技术支持.md) |
| **张琼文** | 基线策略开发 | `policies/baselines/` | [02_张琼文_基线策略开发.md](./team_guides/02_张琼文_基线策略开发.md) |
| **曹晓晗** | LLM 模拟审查员设计 | `reviewer/prompt_templates.py`、`reviewer/llm_reviewer.py` | [03_曹晓晗_LLM模拟审查员.md](./team_guides/03_曹晓晗_LLM模拟审查员.md) |
| **史璟** | 智能审批策略初步拟定 | `policies/smart/smart_policy.py` | [04_史璟_智能审批策略.md](./team_guides/04_史璟_智能审批策略.md) |
| **李易臻 & 朱茵** | 评测、数据分析与报告（内部分工自定） | `evaluation/`、`README.md` / Report | [05_李易臻与朱茵_评测分析与报告.md](./team_guides/05_李易臻与朱茵_评测分析与报告.md) |

---

## 4. 快速上手与运行

### 4.1 安装环境与依赖
```bash
pip install -r requirements.txt
```

### 4.2 运行演示 Demo
运行完整的三分类拦截与预算退化演示：
```bash
python main.py
```

### 4.3 运行自动化单元测试
无需额外依赖，使用 Python 自带的 `unittest` 即可全绿运行所有测试：
```bash
python -m unittest discover -s tests -v
```
（如果安装了 `pytest`，也可直接执行 `pytest -v`）。

### 4.4 按模块 Smoke 验证（组员自测）
各角色详细命令与期望输出见 [`team_guides/`](./team_guides/)。仓库也提供一键脚本：

```bash
python scripts/smoke_reviewer.py      # 曹晓晗：审查员离线自测
python scripts/smoke_smart_policy.py  # 史璟：智能策略三分类自测
python scripts/smoke_evaluation.py    # 评测组：TCR/HITL 指标聚合自测
```

---

## 5. 关键设计规范说明

### 5.1 信息隔离机制（Information Sanitization）
在学术评测中，Reviewer 严禁接触以下 Oracle 信息：

- `ground_truth` / `attack_annotation` / `is_attack` / `target_state`

`reviewer/base.py` 内部实现了 `sanitize_context` 方法，在上下文进入模拟审查员前会自动过滤全部潜在的 Oracle 键值。

### 5.2 决策结果流转
```text
ToolCall 发起
     │
     ▼
ApprovalGate 拦截
     │
     ├── Policy 判定为 AUTO_APPROVE ──> 最终动作: EXECUTE
     ├── Policy 判定为 AUTO_DENY ────> 最终动作: BLOCK
     └── Policy 判定为 ESCALATE
              │
              ├── 预算 k > 0 ──> 消耗 1 点预算 ──> Reviewer 审查 ──> EXECUTE / BLOCK
              └── 预算 k == 0 ──> 降级机制触发 ──> 自动转为 AUTO_DENY ──> BLOCK
```

### 5.3 智能审批策略当前实现

`SmartApprovalPolicy` 当前采用**确定性、无需 Oracle 信息的风险分类器**，暂不调用外部 LLM，因此策略自身的 `token_cost` 为 `0`。主要行为如下：

- 明显安全的只读调用自动放行；但读取 `.ssh`、`.aws`、`.env`、密码、Token、API Key 或私钥等敏感内容时升级人工审查。
- `rm -rf`、数据库删除/清空、强制推送、提示注入等明确危险行为自动拒绝。
- 将凭据或秘密通过上传、发送、发布、Webhook 等远程工具外传时自动拒绝。
- 对普通状态修改调用综合远程副作用、工具危险性、敏感资源、批量范围、临时目录和任务相关性计算风险分数。
- 根据人工预算剩余比例调整自动放行和自动拒绝阈值，把有限的 `ESCALATE` 留给灰区调用；预算真正耗尽后的强制拒绝仍由 `ApprovalGate` 统一执行。

当前自动化验证覆盖智能策略专属测试、端到端测试及全量测试；本分支最近一次本地验证结果为 **25/25 通过**。
