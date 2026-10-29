# Evaluation Reproducibility and Scope

- Source: AgentDojo v0.1.35, suite v1.2.2, workspace.
- Agent and Reviewer: openai/gpt-4o-mini.
- Budgets: 0, 1, 2, 5, 10.
- Policies: Full-approve, Smart Policy, Full-escalate.
- Dataset: 60 attacked configurations, no clean controls.
- 900 configuration rows = 660 recorded model runs
  and 240 reused Full-approve baseline rows.
- Case-level source submission is restricted to S60-001–030.
- Quantitative summaries include all S60-001–060.
- Rule-based, Agent Tokens, retry-inclusive monetary cost,
  and independent experimental replications are missing.
- The standalone Colab runners should be archived and
  integrated with evaluation/runner.py before claiming
  fully reproducible benchmark execution.
- Failure-review rows are candidates, not manually
  validated causal labels.
