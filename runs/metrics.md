# Results (held-out test sets)

## PII pseudonymiser (600 test docs, 1/3 from unseen templates)
| model | char recall | leakage | precision | ms/doc |
|---|---|---|---|---|
| gliner_base | 0.820 | 0.180 | 1.000 | 57.2 |
| gliner_base+rules | 0.995 | 0.005 | 1.000 | 56.9 |
| rules_only | 0.672 | 0.328 | 1.000 | 0.1 |
| gliner_finetuned | 0.905 | 0.095 | 1.000 | 58.7 |
| gliner_finetuned+rules | 1.000 | 0.000 | 1.000 | 59.2 |
| openai_privacy_filter | 0.942 | 0.059 | 0.925 | 695.0 |

## PII: our fine-tuned GLiNER + Italian-format rules (same 600 in-distribution docs)
| model | char recall | leakage | precision | ms/doc |
|---|---|---|---|---|
| ft_thr0.3+rules | 1.000 | 0.000 | 1.000 | 17.2 |
| ft_thr0.2+rules | 1.000 | 0.000 | 1.000 | 16.1 |
| ft_thr0.1+rules | 1.000 | 0.000 | 1.000 | 16.0 |
| ensemble_ft+rules+privacy_filter | 1.000 | 0.000 | 0.968 | 317.3 |

## PII: OUT-OF-DISTRIBUTION (Gretel finance test split, never trained on)
| model | char recall | leakage | precision | ms/doc |
|---|---|---|---|---|
| gliner_base | 0.868 | 0.132 | 0.725 | 24.5 |
| ours_finetuned+rules | 0.930 | 0.070 | 0.886 | 23.7 |
| openai_privacy_filter | 0.685 | 0.315 | 0.589 | 435.6 |
| ours+privacy_filter_ensemble | 0.967 | 0.033 | 0.654 | 455.7 |

Live workspace (86 docs): 0/430 PII values leaked (0.0%).

## LLM tasks
| model | triage.exact | qa.ans_correct | qa.ans_cited | qa.unans_abstain | qa.hallucinated | extract_facts.key_recall | latency_s |
|---|---|---|---|---|---|---|---|
| student_base | 0.91 | 0.9904 | 1.0 | 1.0 | 0.0 | 0.6708 | 1.8367 |
| student_distilled | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.7792 | 1.2368 |
| teacher | 0.955 | 1.0 | 1.0 | 1.0 | 0.0 | 0.6708 | 1.5852 |
