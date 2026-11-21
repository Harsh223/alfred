# 🦇 ALFRED — Agentic Ledger For Regulated Enterprise Decisions

**An AI colleague a bank can trust: it speaks first, knows what it doesn't know, and never acts without a person's approval.**
Built in one day for the GDG *Agentic AI in companies* hackathon (Turin, 21 Nov 2026 · track sponsor Ariete Tech Solutions) for a fictional bank, **Lumen Bank**.
Everything runs on **open-weight models on the bank's own infrastructure** — no customer data ever reaches a third-party AI.

> Challenge A (Company Brain) **and** Challenge B (Back-Office Autopilot): B is what makes A possible. A bank can't let an AI read its inbox until personal data is masked, and the brain's most useful actions are the autopilot's reminders — each waiting for a human click.

## What it does

| | |
|---|---|
| **🔒 Privacy shield** | A fine-tuned PII model + Italian-format rules (IBAN mod-97, codice fiscale, P.IVA, CIE, CAP, health terms) replace every person/ID with a stable token (`<CLIENT_0042>`) *before* any LLM sees text. Real values live only in a role-gated vault and appear on screen only for authorised roles. |
| **🤖 Back-office autopilot** | Overdue-loan reminders end to end: arrears extract + payments in → policy rules + an independent model triage → exceptions stop for a human (deceased, vulnerable, forbearance, complaint, dispute, unmatched payment, > €5k, **open AML alert → never contact: no tipping-off**) → approved items become real letters + a PEC-gateway batch → full audit trail. |
| **🧠 Company brain** | Morning brief at 07:30 (speaks first) · answers only from **human-approved memory** with citations · knows who's asking (finance ≠ IT) · says *"I don't know"* · only **proposes** actions · Teams-style chat + morning email. |
| **✅ Independent checker** | A second, different model (Qwen3.8-27B) must confirm every answer is supported by its sources and answers the question asked — otherwise the user gets "I don't know". |
| **🛡️ Red-team arena** | A 180B model attacked the system **3,947 times** (9 categories, EN/IT, obfuscation). Results and the full pipeline are in this repo. |
| **📊 Dashboard + API** | Public metrics dashboard (`/dashboard`) and a REST API (`/v1`, OpenAPI at `/api/docs`) so other teams can use and test it, plus a public **Attack ALFRED** arena (`/arena`) where rival teams get keys, attack the API and file breach reports — see [docs/API.md](docs/API.md). |

## Architecture

```
raw input ──▶ ① PRIVACY SHIELD (GLiNER-bank + rules) ──▶ DuckDB (masked docs · vault 🔒 · memory · actions · audit)
                                                              │
        ┌─────────────────────────────────────────────────────┴───────────────────────────────┐
        ▼                                                                                     ▼
② AUTOPILOT: rules decide · 9B cross-checks ·                    ③ BRAIN: security gate → router (from scratch) →
  exceptions → human · CCD2/AI-Act letters                         role filter BEFORE search → approved memory →
                                                                   9B answer + citations → 27B checker → or "I don't know"
        └───────────────────────────────┬──────────────────────────────────────────────────────┘
                                        ▼
                ④ HUMAN APPROVAL (one click · four-eyes on chat requests and new facts)
                                        ▼
             OUTBOX (letters + PEC batch, real names filled in only now)  ──▶  AUDIT TRAIL
```

### Models — who does what
| Model | Origin | Runs on | Job |
|---|---|---|---|
| **GLiNER-bank** + rules | fine-tuned `urchade/gliner_multi_pii-v1` on 4k bank docs + Gretel finance | CPU | mask personal data |
| **Assistant** Qwen3.5-9B + LoRA | **distilled** from Qwen3.8-Flash-Next 180B (only teacher answers that matched gold labels were kept) | a single GPU | answers, triage, briefs, fact extraction |
| **Checker** Qwen3.8-27B-FP8 | off-the-shelf, different model family member | a single GPU | verifies every answer against sources |
| **Router** | **trained from scratch** (3.1M params, fastText-style) | CPU, 0.15 ms | intent: my work · knowledge · customer · action · help · off-topic |
| **Signal reader** Qwen3.5-0.8B | distilled from our 9B | CPU/GPU | hardship / dispute / death / complaint in customer emails |
| **Guard** Qwen3.5-0.8B | trained on the arena attacks + 4 public injection sets | CPU/GPU | learned attack detector |
| Teacher Qwen3.8-Flash-Next 180B MoE | — | a multi-GPU server (training time only) | data generation, attacks, judging — **not needed in production** |

## Results (held-out, all reproducible from this repo)
| Test | Result |
|---|---|
| Jury checks — every Challenge A + B requirement, automated (`tests/jury_checks.py`) | **11/11** (also on a 10× bank and a calibrated "realism" bank) |
| Human battery — casual, Italian, vague, role abuse (`tests/human_battery.py`) | **57/57** |
| Manual HTTP red team — forged cookies, direct-POST approvals, XSS, SQLi, traversal, memory poisoning, four-eyes (`tests/redteam_http.py`) | **26/26** |
| AI red-team arena — 3,947 prompts × 3 rounds (`tests/redteam/`) | **0 real-data leaks · 0 actions without approval · attack success 1.28% → 0.00%** · false refusals 31% → 13.6% |
| Distilled 9B vs its 180B teacher — loan triage | **100% vs 95.5%** |
| PII recall — our bank docs / live workspace | **100% / 0 of 430 values leaked** |
| PII recall — external sets (Gretel, Nemotron, ai4privacy) with ensemble | **96.7 – 99.6%** |
| Concurrency — 40 simultaneous users | **0 errors** |

Full tables: [runs/metrics.md](runs/metrics.md) · red team: [docs/REDTEAM.md](docs/REDTEAM.md) · data: [docs/DATA.md](docs/DATA.md) · compliance (GDPR, AI Act, DORA, CCD2, AML): [docs/COMPLIANCE.md](docs/COMPLIANCE.md).

## Run it
```bash
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn duckdb openai jinja2 faker torch
.venv/bin/python data/scripts/gen_bank.py            # synthetic Lumen Bank (seed 7)
# point at self-hosted, OpenAI-compatible inference servers (vLLM); set STUDENT_TOKEN / VERIFIER_TOKEN if they need auth (LLM_AUTH_HEADER picks the header name); without them ALFRED runs in a safe offline mode
export STUDENT_URL=http://localhost:8002/v1  VERIFIER_URL=http://localhost:8000/v1
.venv/bin/uvicorn app.main:app --port 8080            # → http://127.0.0.1:8080  (demo sign-in: /as/rm_credit?next=/today)
.venv/bin/python tests/jury_checks.py && .venv/bin/python tests/human_battery.py
```
Training/eval pipeline: `llm/` (distillation, LoRA, evals), `anonymizer/` (PII training/eval), `brain/router.py` (router), `tests/redteam/` (arena).

## Repo map
```
app/          FastAPI web app + REST API + dashboard + arena
brain/        retrieval, roles, router, security gate, checker client, briefs
autopilot/    reminder engine, outbox (letters + PEC batch)
anonymizer/   PII model training, rules, evaluation, ensemble
llm/          prompts, distillation, LoRA training, evaluation runners
data/         synthetic bank (DuckDB), task sets, PII sets, red-team attacks, real open samples
tests/        jury checks, human battery, HTTP red team, stress test, red-team arena
docs/         SYSTEM, SPEC, API, DATA, COMPLIANCE, REDTEAM, UI research
runs/         metrics and reports (no secrets, no model weights)
```

## Licences & honesty
- Code: Apache-2.0. **All bank data is synthetic** (Faker, fictional names); real-world samples are public-domain/CC (CFPB, Banking77) — see `data/real/README.md`.
- Models: Qwen3.5 / Qwen3.8 (Apache-2.0), Qwen3.8-Flash-Next (Qwen community licence), GLiNER PII (Apache-2.0), OpenAI privacy-filter (Apache-2.0), Nemotron-PII data (CC-BY-4.0). ai4privacy data was used **for evaluation only** (non-commercial licence).
- Production gaps we state openly: vault encryption with a KMS, SSO/MFA instead of demo sign-in, DPIA + records of processing, DORA register of information — see `docs/COMPLIANCE.md`.
