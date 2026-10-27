# Demo 输入与输出快照

保存日期：2026-10-27（Asia/Singapore）。

| 文件 | 内容 |
| --- | --- |
| [input.json](input.json) | 实际任务上下文、四次工具调用、策略配置、初始预算、Mock Reviewer 配置、Python 版本、Git 基础提交和源码 SHA-256。 |
| [output.txt](output.txt) | `python main.py` 的完整标准输出，按原始字节保存。 |
| [stderr.txt](stderr.txt) | 完整标准错误输出，包括预期的预算耗尽警告，按原始字节保存。 |
| [decisions.json](decisions.json) | 四个策略的全部 16 次决策，包含理由、规则元数据、Reviewer 结果，以及调用前后的预算状态；省略每次运行都会变化的时间戳。 |

结构化输入与决策来自原 Demo 的实际运行。采集时的标准输出和错误输出已与一次独立的命令行运行对照，归一化换行符后完全一致；文本文件保留命令行运行的原始字节。

Rule-based 规则版本：`3`；`deny_dangerous=True`；`trusted_domains=[]`。

| 策略 | 初始预算 | 按调用顺序的 Gate 动作 | 实际是否进入 Reviewer |
| --- | --- | --- | --- |
| `full_approve` | 0 | EXECUTE, EXECUTE, EXECUTE, EXECUTE | False, False, False, False |
| `full_escalate` | 1 | EXECUTE, BLOCK, BLOCK, BLOCK | True, False, False, False |
| `rule_based` | 2 | EXECUTE, EXECUTE, EXECUTE, BLOCK | False, True, True, False |
| `smart` | 1 | EXECUTE, EXECUTE, BLOCK, BLOCK | False, True, False, False |

Rule-based 的最后一次调用由 Gate 因审核预算耗尽直接 BLOCK。

## 复现方式

在仓库根目录，使用快照对应的源码及配置运行：

```text
python main.py
```

`input.json` 记录的是 Demo 在代码中构造的输入，`main.py` 不接受此 JSON 作为命令行输入文件。复现时可将新的 stdout/stderr 与保存文件对照。源码哈希用于核对本地实现；本快照包含 Git 基础提交之外尚未提交的改动。

本快照用于合成工具调用和 Mock Reviewer 的离线路由演示，不代表正式 AgentDojo 评测成绩。各策略的演示预算不同。快照中的 Smart Policy 为当前本地骨架实现，尚未采用未合并 PR 中的新实现。
