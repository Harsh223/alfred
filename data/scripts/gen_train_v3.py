#!/usr/bin/env python3
"""Extra SFT data (v3) with GOLD targets for the weak spots. Never overlaps the test sets (different seeds, phrasings checked).
  - triage at rule boundaries (gold from the deterministic rules)
  - policy questions in many phrasings (typos / Italian / casual), written by our 9B, with a gold answer built from the policy sentence + citation
  - near-miss unanswerables -> I DON'T KNOW
-> data/sft_v3_extra.jsonl (chat format)"""
import json, os, random, re, sys, concurrent.futures as cf
import duckdb
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../llm"))
from prompts import messages, ABSTAIN
from openai import OpenAI

R = random.Random(777); ROOT = os.path.join(os.path.dirname(__file__), "..")
test_qs = {json.loads(l)["input"]["question"].strip().lower() for f in ("qa_hard", "qa_test") for l in open(f"{ROOT}/tasks/{f}.jsonl")}
con = duckdb.connect(f"{ROOT}/bank.duckdb", read_only=True)
pol = {t: (d, a) for d, t, a in con.execute("select doc_id, title, anon_text from documents where kind='policy'").fetchall()}
other = [{"doc_id": d, "text": a[:700]} for d, a in con.execute("select doc_id, anon_text from documents where kind<>'policy' order by doc_id").fetchall()]
rows = []
def add(task, inp, target): rows.append({"messages": messages(task, inp) + [{"role": "assistant", "content": target}]})

# ---- triage boundaries
FLAGS = ["deceased", "vulnerable", "forbearance", "complaint_open", "dispute"]
REASON = {"send_reminder_email": "1-30 days past due: polite email reminder.", "send_formal_pec_and_fee": "31-60 days: formal PEC reminder plus EUR 15 late fee.",
          "final_notice_and_escalate_collections": "61-90 days: final notice and hand-over to collections.", "escalate_legal": "Over 90 days: escalate to legal."}
for k in range(1500):
    dpd = R.choice([1, 2, 15, 28, 29, 30, 31, 33, 45, 58, 59, 60, 61, 63, 75, 88, 89, 90, 91, 94, 120, 200, 400])
    amt = R.choice([4999.99, 5000.0, 5000.01, 4999.0, 5001.0, 30.0, 999.0, 2500.0, 7500.0, 15000.0, round(R.uniform(10, 12000), 2)])
    flags = R.sample(FLAGS, R.choice([0, 0, 0, 1, 1, 2, 3]))
    c = {"case_id": f"TR3-{k:05d}", "product": R.choice(["mutuo", "prestito", "fido_pmi"]), "days_past_due": dpd, "amount_overdue": amt,
         "bucket": "1-30" if dpd <= 30 else "31-60" if dpd <= 60 else "61-90" if dpd <= 90 else "90+", "recent_payment": R.random() < .2,
         "customer_flags": flags, "segment": R.choice(["retail", "sme"]), "customer": f"<CLIENT_{R.randint(1, 400):04d}>", "loan": f"<LOAN_{R.randint(1, 500):04d}>"}
    if flags: d, e, why = "hold_for_human", flags[0], f"Customer flag '{flags[0]}': human review required, no automatic reminder."
    elif c["recent_payment"]: d, e, why = "hold_for_human", "unmatched_payment", "Recent partial/unmatched payment: verify before any reminder."
    elif amt > 5000: d, e, why = "hold_for_human", "high_amount", f"Overdue amount {amt:.2f} is above EUR 5,000: human review required."
    else: d, e, why = {"1-30": "send_reminder_email", "31-60": "send_formal_pec_and_fee", "61-90": "final_notice_and_escalate_collections", "90+": "escalate_legal"}[c["bucket"]], None, ""
    why = why or REASON[d]
    add("triage", c, json.dumps({"decision": d, "exception": e, "reason": why}))

# ---- policy facts: (policy, seed question, key, gold answer)
FACTS = [("Credit Policy v3 (2026)", "maximum SME credit line without committee approval", "EUR 250,000", "The maximum SME credit line without credit-committee approval is EUR 250,000 (Credit Policy v3)."),
         ("Credit Policy v3 (2026)", "maximum instalment-to-income ratio for mortgages", "33%", "The maximum instalment-to-income ratio for mortgages is 33% (Credit Policy v3)."),
         ("Credit Policy v3 (2026)", "Confidi guarantee coverage", "80%", "Confidi guarantees cover up to 80% for amounts up to EUR 100,000."),
         ("Reminders and Collections Procedure", "late fee with the formal PEC reminder", "EUR 15", "The formal PEC reminder (31-60 days past due) carries a EUR 15 late fee."),
         ("Reminders and Collections Procedure", "what happens after 90 days past due", "legal", "After 90 days past due the case goes to the legal department."),
         ("Reminders and Collections Procedure", "when human review is required for reminders", "human review", "Deceased or vulnerable customers, forbearance, open complaints and overdue amounts above EUR 5,000 always require human review."),
         ("KYC and Customer Due Diligence Procedure", "due diligence renewal period for high-risk customers", "12 months", "Due diligence must be renewed every 12 months for high-risk customers (every 24 months for low-risk)."),
         ("Core Banking Nightly Batch Runbook", "which job to re-run if the nightly batch fails", "RICONC-02", "Re-run job RICONC-02 after checking free disk space on db-core-03; escalate to the vendor after two consecutive failures."),
         ("Bank of Italy Reporting Deadlines", "deadline of the Q3 supervisory report", "25/11/2026", "The Q3 supervisory report (Matrice dei conti) must be submitted by 25/11/2026."),
         ("Branch Hours and Services", "branch opening hours", "8:30", "Branches are open Monday to Friday 8:30-13:30 and 14:30-16:00.")]
st = os.environ
cli = OpenAI(base_url=st["STUDENT_URL"], api_key="x", default_headers=({st["LLM_AUTH_HEADER"]: st["STUDENT_TOKEN"]} if st.get("LLM_AUTH_HEADER") else {"Authorization": f"Bearer {st['STUDENT_TOKEN']}"}), timeout=120)
def paraphrases(topic):
    p = (f"Write 24 different ways a bank employee might ask an internal assistant about: {topic}. Mix: casual with typos, formal, very short, "
         "Italian, Italian-English mix, indirect. One per line, no numbering.")
    r = cli.chat.completions.create(model="student", messages=[{"role": "user", "content": p}], temperature=1.0, max_tokens=900,
                                    extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    return [re.sub(r"^\s*[-*\d.)]+\s*", "", l).strip().strip('"') for l in r.choices[0].message.content.splitlines() if 5 < len(l.strip()) < 200]
with cf.ThreadPoolExecutor(10) as ex: P = list(ex.map(lambda f: paraphrases(f[1]), FACTS))
nq = 0
for (t, _, key, gold), qs in zip(FACTS, P):
    d, a = pol[t]
    for q in qs:
        if q.strip().lower() in test_qs: continue
        for _ in range(2):
            ctx = [{"doc_id": d, "text": a}] + R.sample(other, 3)
            if t == "Credit Policy v3 (2026)" and R.random() < .3: ctx.append({"doc_id": pol["Credit Policy v2 (2025)"][0], "text": pol["Credit Policy v2 (2025)"][1]})
            R.shuffle(ctx); add("qa", {"question": q, "chunks": ctx}, f"{gold} [{d}]"); nq += 1
# near-miss unanswerables (different from the test ones)
NEAR = [("What is the SME credit line limit for German subsidiaries?", "Credit Policy v3 (2026)"), ("What was the mortgage ratio in 2021?", "Credit Policy v2 (2025)"),
        ("Which job do we re-run when the monthly report batch fails?", "Core Banking Nightly Batch Runbook"), ("What fee applies to a fourth email reminder?", "Reminders and Collections Procedure"),
        ("When is the Q1 2027 supervisory report due?", "Bank of Italy Reporting Deadlines"), ("Do branches open on Sunday?", "Branch Hours and Services"),
        ("How often do we review medium-risk customers in France?", "KYC and Customer Due Diligence Procedure"), ("What is the Confidi coverage above EUR 500,000?", "Credit Policy v3 (2026)")]
for q, t in NEAR:
    for _ in range(12):
        ctx = [{"doc_id": pol[t][0], "text": pol[t][1]}] + R.sample(other, 3); R.shuffle(ctx); add("qa", {"question": q, "chunks": ctx}, ABSTAIN)
R.shuffle(rows)
with open(f"{ROOT}/sft_v3_extra.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print({"rows": len(rows), "triage": 1500, "qa_paraphrase": nq, "near_miss": len(NEAR) * 12})
