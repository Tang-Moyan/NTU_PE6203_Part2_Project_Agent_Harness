# Cost and Data Quality Analysis

## Evaluation Scope

60 attacked AgentDojo workspace configurations, three policies, and five budgets (k=0,1,2,5,10).

900 configuration rows contain 660 measured runs and 240 reused Full-approve baseline rows.

## Reviewer Token and HITL Analysis

| k | Policy | Safe TCR | All HITL | Safe HITL | Reviewer Tokens |
|---|---|---:|---:|---:|---:|
| 0 | Full-approve | 86.7% | 0 | 0 | 0 |
| 0 | Full-escalate | 0.0% | 0 | 0 | 0 |
| 0 | Smart Policy | 81.7% | 0 | 0 | 0 |
| 1 | Full-approve | 86.7% | 0 | 0 | 0 |
| 1 | Full-escalate | 30.0% | 60 | 18 | 36,985 |
| 1 | Smart Policy | 95.0% | 19 | 16 | 32,255 |
| 2 | Full-approve | 86.7% | 0 | 0 | 0 |
| 2 | Full-escalate | 53.3% | 107 | 52 | 89,027 |
| 2 | Smart Policy | 93.3% | 27 | 22 | 43,744 |
| 5 | Full-approve | 86.7% | 0 | 0 | 0 |
| 5 | Full-escalate | 50.0% | 154 | 50 | 145,050 |
| 5 | Smart Policy | 93.3% | 28 | 26 | 42,848 |
| 10 | Full-approve | 86.7% | 0 | 0 | 0 |
| 10 | Full-escalate | 51.7% | 149 | 50 | 142,444 |
| 10 | Smart Policy | 93.3% | 27 | 24 | 42,273 |

## Cost Interpretation

- Smart Policy is deterministic and uses no policy LLM tokens.
- Reviewer tokens represent recorded scored-attempt usage.
- Agent token usage was not collected in these result CSVs.
- Full API monetary cost therefore remains unknown.
- Reused baseline rows are not additional measured runs.

## Data Quality and Limitations

- Four original legacy runs appear as 20 expanded rows.
- Legacy missing input/output token components correspond to zero-review Full-approve runs.
- All 900 configurations have completed status.
- No approval-budget violations were observed.
- UNCONFIRMED exposure does not prove successful defense.
- Each measured configuration has only one recorded run.
- Clean controls, Rule-based policy and other suites are not included in this experiment.
- No statistical significance or causal optimal-k claim is made.