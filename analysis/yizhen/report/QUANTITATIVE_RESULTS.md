# Quantitative Results

## Experimental Setup

We evaluated 60 attacked configurations in the AgentDojo workspace suite, using Full-approve, Smart Policy and Full-escalate under k = 0, 1, 2, 5, 10.

The evaluation contains 900 configuration rows, including 240 reused Full-approve baseline rows. Each measured configuration has one recorded run.

## Main Results

| k | Policy | Safe TCR | ASR | HITL | Reviewer Tokens |
|---|---|---:|---:|---:|---:|
| 0 | Full-approve | 86.7% | 10.0% | 0 | 0 |
| 0 | Full-escalate | 0.0% | 0.0% | 0 | 0 |
| 0 | Smart Policy | 81.7% | 0.0% | 0 | 0 |
| 1 | Full-approve | 86.7% | 10.0% | 0 | 0 |
| 1 | Full-escalate | 30.0% | 0.0% | 60 | 36985 |
| 1 | Smart Policy | 95.0% | 3.3% | 19 | 32255 |
| 2 | Full-approve | 86.7% | 10.0% | 0 | 0 |
| 2 | Full-escalate | 53.3% | 1.7% | 107 | 89027 |
| 2 | Smart Policy | 93.3% | 6.7% | 27 | 43744 |
| 5 | Full-approve | 86.7% | 10.0% | 0 | 0 |
| 5 | Full-escalate | 50.0% | 0.0% | 154 | 145050 |
| 5 | Smart Policy | 93.3% | 3.3% | 28 | 42848 |
| 10 | Full-approve | 86.7% | 10.0% | 0 | 0 |
| 10 | Full-escalate | 51.7% | 0.0% | 149 | 142444 |
| 10 | Smart Policy | 93.3% | 5.0% | 27 | 42273 |

## Interpretation

In this single-run evaluation, Smart Policy obtained its highest observed Safe TCR at k=1. Increasing the approval budget did not produce a monotonic improvement.

Reviewer Token consumption was generally lower for Smart Policy than for Full-escalate.

## Limitations

- The 60 configurations are not 60 independent user tasks.
- All configurations are attacked, using workspace only.
- Rule-based and clean controls are not included.
- Agent Tokens and retry-inclusive monetary costs are unavailable.
- Full-approve was reused across budget values.
- No replicated runs or statistical significance claims.