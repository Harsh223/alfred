# Lumen Bank (fictional, Turin): shared contract

Everything reads and writes `data/bank.duckdb` (built by `data/scripts/gen_bank.py`, seeded and deterministic).
The raw (un-pseudonymised) text exists only in `raw_*` tables and the vault. The app and the LLM only see `*_anon`.

## DuckDB tables
- `customers(customer_id VARCHAR PK 'NDG0000123', full_name, codice_fiscale, birth_date, email, phone, address, iban, segment 'retail'|'sme', partita_iva NULL, flags VARCHAR[] -- 'forbearance','deceased','vulnerable','complaint_open','dispute')`
- `loans(loan_id 'MUT-2024-00042', customer_id, product 'mutuo'|'prestito'|'fido_pmi', principal, rate, monthly_installment, start_date, status 'ok'|'arrears')`
- `installments(loan_id, due_date, amount_due, amount_paid, paid_date NULL)`  -- arrears = due and not fully paid
- `payments(payment_id, customer_id, loan_id NULL, amount, value_date, reference_text)`  -- includes unmatched / partial payments
- `documents(doc_id 'EML-0001', kind 'email'|'chat'|'ticket'|'policy'|'kyc_note'|'credit_memo', department 'credit'|'it'|'compliance'|'all', created_at, title, author_role, raw_text, anon_text, spans JSON)`
  - `spans`: list of `{start,end,label,value}` on raw_text. Labels: PERSON, TAX_CODE, VAT_NUMBER, IBAN, CARD_NUMBER, EMAIL, PHONE, ADDRESS, DATE_OF_BIRTH, ID_DOC, CUSTOMER_ID, LOAN_ID
- `vault(pseudonym '<CLIENT_0042>', label, real_value)`  -- consistent pseudonyms across all docs
- `memory(fact_id, doc_id, department, text, status 'pending'|'approved'|'rejected', decided_by, decided_at)`
- `actions(action_id, kind 'send_reminder'|'post_late_fee'|'escalate'|'draft_email', case_id, payload JSON, status 'proposed'|'approved'|'rejected'|'executed', proposed_by 'brain'|'autopilot', approved_by, ts)`
- `cases(case_id, loan_id, customer_id, days_past_due, amount_overdue, bucket '1-30'|'31-60'|'61-90'|'90+', decision, exception VARCHAR NULL, reason, status)`
- `audit(ts, actor, role, event, object_id, detail JSON)`

## Roles (from login only, never from chat text)
- `rm_credit` (finance: Relationship Manager). Departments: credit, compliance, all. May de-pseudonymise.
- `it_support` (tech). Departments: it, all. Pseudonyms only, no customer credit data.
- `compliance` (optional). Departments: compliance, credit, all. May de-pseudonymise.

## Autopilot (Challenge B, overdue-loan reminders) rules
- bucket by days_past_due; 1-30 → gentle reminder (email); 31-60 → formal reminder (PEC) + late fee €15; 61-90 → final notice + escalate to collections; 90+ → escalate to legal.
- EXCEPTIONS (stop, ask a human): customer flag in {deceased, vulnerable, forbearance, complaint_open, dispute}; unmatched/partial payment in last 10 days; amount_overdue > €5,000; pseudonym/record mismatch.
- Irreversible (need approval): send_reminder, post_late_fee, escalate. Everything else is automatic.

## LLM endpoints (OpenAI-compatible)
- `STUDENT_URL` (distilled Qwen3.5 on a single GPU, model name `student`), `TEACHER_URL` (Qwen3.8-Flash-Next-FP8 on a multi-GPU server, training time only, model `teacher`), `VERIFIER_URL` (checker Qwen3.8-27B, model `verifier`). All are self-hosted, OpenAI-compatible inference servers (vLLM). App falls back student → teacher → offline stub.
- Auth: optional `STUDENT_TOKEN` / `TEACHER_TOKEN` / `VERIFIER_TOKEN` (shared fallback `LLM_TOKEN`), sent as `Authorization: Bearer <token>`; set `LLM_AUTH_HEADER` to send the raw token under a different header name instead.
- Tasks + prompt formats live in `llm/prompts.py` (shared by distillation, eval and the app):
  - `qa`: question + retrieved chunks `[doc_id] text` → answer citing `[doc_id]`, or exactly `I DON'T KNOW` when unsupported.
  - `extract_facts`: anon doc → JSON list of facts `{text}`.
  - `triage`: case JSON + rules → JSON `{decision, exception|null, reason}`.
  - `brief`: role + today's events → 3-5 bullet morning brief with `[doc_id]` citations.
