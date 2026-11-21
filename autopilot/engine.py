"""Challenge B: overdue-loan reminder autopilot (English).
Raw input = today's arrears extract (cases_input) + customer flags + payments. Deterministic policy rules decide; the LLM (distilled
student) independently triages every case and is cross-checked; disagreements and exceptions stop for a human; every irreversible
step (send, fee, escalate) is only PROPOSED until a person approves it. Everything is written to the audit trail."""
import json, re
from concurrent.futures import ThreadPoolExecutor
from brain import core as C
from brain import llm

POLICY = "Reminder & collections procedure (POL-0003)"
DECISIONS = {"1-30": "send_reminder_email", "31-60": "send_formal_pec_and_fee", "61-90": "final_notice_and_escalate_collections", "90+": "escalate_legal"}
LABEL = {"send_reminder_email": "Polite reminder by email", "send_formal_pec_and_fee": "Formal reminder by certified email (PEC) + €15 late fee",
         "final_notice_and_escalate_collections": "Final notice + hand-over to collections", "escalate_legal": "Escalate to legal",
         "hold_for_human": "Stopped: human review"}
EXC_LABEL = {"deceased": "Customer deceased", "vulnerable": "Vulnerable customer", "forbearance": "Customer in forbearance",
             "complaint_open": "Open complaint", "dispute": "Dispute in progress", "unmatched_payment": "Partial/unmatched payment in last 10 days",
             "high_amount": "Overdue amount above €5,000", "record_mismatch": "Pseudonym / record mismatch", "model_disagreement": "Model disagrees with rules"}
MANUAL_MIN, REVIEW_MIN = 12, 1   # assumption: 12 min to check one case by hand; 1 min to approve a prepared one


def bucket(d):
    return "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"


def rules(case):
    """Same precedence as the bank policy: customer flag > recent payment > amount > bucket."""
    if case["customer_flags"]:
        f = case["customer_flags"][0]
        if f == "aml_alert_open":
            return "hold_for_human", f, "Open AML alert on this customer: no contact of any kind (tipping-off risk). Refer to Compliance."
        return "hold_for_human", f, f"Customer flag '{f}': no automatic reminder (policy requires human review)."
    if case["recent_payment"]:
        return "hold_for_human", "unmatched_payment", "Partial or unmatched payment in the last 10 days: verify before sending a reminder."
    if case["amount_overdue"] > 5000:
        return "hold_for_human", "high_amount", "Overdue amount above €5,000: human review required."
    b = case["bucket"]
    return DECISIONS[b], None, {"1-30": "1-30 days past due: polite email reminder.", "31-60": "31-60 days: formal PEC reminder + €15 late fee.",
                                "61-90": "61-90 days: final notice + hand-over to collections.", "90+": "Over 90 days: escalate to legal."}[b]


def load_input():
    """Today's arrears extract joined with what the rules need. Customer and loan are referenced by pseudonym only."""
    ccols = [r[0] for r in C.rows("DESCRIBE customers")]
    lcols = [r[0] for r in C.rows("DESCRIBE loans")]
    cps = "c.pseudonym" if "pseudonym" in ccols else "NULL"
    lps = "l.pseudonym" if "pseudonym" in lcols else "NULL"
    src = "cases_input" if "cases_input" in [r[0] for r in C.rows("SHOW TABLES")] else "cases"
    rows = C.q(f"""SELECT k.case_id, k.loan_id, k.customer_id, k.days_past_due, k.amount_overdue, k.bucket, k.recent_payment,
                     l.product, c.segment, c.flags, {cps} AS customer_ps, {lps} AS loan_ps
                   FROM {src} k JOIN loans l USING(loan_id) JOIN customers c ON c.customer_id = k.customer_id ORDER BY k.case_id""")
    # AML: customers named in an open AML alert must not be contacted (tipping-off risk) -> exception for Compliance
    aml_ps = {m for (t,) in C.rows("SELECT anon_text FROM documents WHERE department='aml'") for m in re.findall(r"<CLIENT_\d+>", t)}
    out = []
    for r in rows:
        rp = r["recent_payment"]
        if rp is None:
            rp = bool(C.q("SELECT 1 FROM payments WHERE customer_id=? AND value_date >= ?::DATE - INTERVAL 10 DAY", [r["customer_id"], C.today()]))
        out.append({"case_id": r["case_id"], "product": r["product"], "days_past_due": int(r["days_past_due"]), "amount_overdue": float(r["amount_overdue"]),
                    "bucket": r["bucket"] or bucket(int(r["days_past_due"])), "recent_payment": bool(rp), "customer_flags": (["aml_alert_open"] if r["customer_ps"] in aml_ps else []) + list(r["flags"] or []),
                    "segment": r["segment"], "customer": r["customer_ps"] or "<?>", "loan": r["loan_ps"] or "<?>",
                    "_loan_id": r["loan_id"], "_customer_id": r["customer_id"]})
    return out


def _llm_triage(case):
    view = {k: v for k, v in case.items() if not k.startswith("_")}
    txt, model = llm.chat(C.PM("triage", view), max_tokens=160, temperature=0.0)
    if not txt:
        return None, "stub"
    try:
        return json.loads(re.search(r"\{.*\}", txt, re.S).group(0)), model
    except Exception:
        return None, model


def letter(case, channel):
    if channel == "email":
        return (f"Dear {case['customer']}, this is a friendly reminder that the instalment on your loan {case['loan']} is {case['days_past_due']} days "
                f"overdue (amount due €{case['amount_overdue']:,.2f}). If you have already paid, please ignore this message. "
                f"If you are having difficulty paying, contact us: we can discuss a payment plan or other forbearance options, and you can get free, independent debt advice. — Lumen Bank")
    return (f"To {case['customer']}: we formally notify you that loan {case['loan']} has an overdue amount of €{case['amount_overdue']:,.2f} "
            f"({case['days_past_due']} days). Please settle within 15 days. "
            f"If you are in financial difficulty, contact us before then: we will assess forbearance options such as a payment plan, and you can get free, independent debt advice. — Lumen Bank, Credit Department")


import threading as _th
_RUN_LOCK = _th.Lock()


def run(actor, role, use_llm=True):
    """Serialised: a second click while a run is in progress waits for it instead of corrupting the case table."""
    if not _RUN_LOCK.acquire(blocking=False):
        C.audit(actor, role, "autopilot_run_skipped", None, {"reason": "a run is already in progress"})
        _RUN_LOCK.acquire()          # wait for the running one, then return its fresh KPIs
        _RUN_LOCK.release()
        return kpis()
    try:
        return _run(actor, role, use_llm)
    finally:
        _RUN_LOCK.release()


def _run(actor, role, use_llm=True):
    """Process the whole arrears extract. Returns KPIs."""
    C.x("DELETE FROM cases"); C.x("DELETE FROM triage_log")
    C.x("DELETE FROM actions WHERE proposed_by='autopilot' AND status='proposed'")
    cases = load_input()
    C.audit(actor, role, "autopilot_run_started", None, {"cases": len(cases), "policy": POLICY})
    if use_llm:
        with ThreadPoolExecutor(16) as ex:
            tri = list(ex.map(_llm_triage, cases))
    else:
        tri = [(None, "stub")] * len(cases)
    for case, (t, model) in zip(cases, tri):
        decision, exc, reason = rules(case)
        llm_dec = (t or {}).get("decision"); llm_exc = (t or {}).get("exception")
        llm_exc = None if llm_exc in (None, "", "null", "None") else llm_exc
        C.x("INSERT INTO triage_log VALUES (?,?,?,?,?,?, now())", [case["case_id"], decision, exc, llm_dec, llm_exc, model])
        if t and decision != "hold_for_human" and llm_dec and llm_dec != decision:
            exc, reason = "model_disagreement", f"Rules say '{decision}' but the model says '{llm_dec}': stopped for human review."
            decision = "hold_for_human"
        if case["customer"] == "<?>":
            decision, exc, reason = "hold_for_human", "record_mismatch", "No pseudonym found for this customer record: stopped."
        status = "exception" if decision == "hold_for_human" else "awaiting_approval"
        C.x("""INSERT INTO cases (case_id, loan_id, customer_id, days_past_due, amount_overdue, bucket, recent_payment, decision, exception, reason, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [case["case_id"], case["_loan_id"], case["customer"], case["days_past_due"], case["amount_overdue"],
                                                  case["bucket"], case["recent_payment"], decision, exc, reason, status])
        C.audit("autopilot", "system", "case_evaluated", case["case_id"],
                {"input": {k: v for k, v in case.items() if not k.startswith("_")}, "rule": reason, "decision": decision, "exception": exc,
                 "model": model, "model_decision": llm_dec, "model_reason": (t or {}).get("reason")})
        if status != "awaiting_approval":
            continue
        acts = []
        if case["bucket"] in ("1-30", "31-60", "61-90"):
            ch = "email" if case["bucket"] == "1-30" else "PEC"
            acts.append(("send_reminder", {"channel": ch, "to": case["customer"], "body": letter(case, ch)}))
        if case["bucket"] == "31-60":
            acts.append(("post_late_fee", {"amount_eur": 15, "loan": case["loan"]}))
        if case["bucket"] in ("61-90", "90+"):
            acts.append(("escalate", {"to": "collections" if case["bucket"] == "61-90" else "legal department", "loan": case["loan"]}))
        for i, (kind, payload) in enumerate(acts):
            C.x("INSERT INTO actions VALUES (?,?,?,?, 'proposed', 'autopilot', NULL, now())",
                [f"A-{case['case_id']}-{i + 1}", kind, case["case_id"], json.dumps(payload, ensure_ascii=False)])
    k = kpis()
    C.audit(actor, role, "autopilot_run_finished", None, k)
    return k


def kpis():
    c = C.q("SELECT count(*) n, count(*) FILTER (WHERE status IN ('exception','held')) e FROM cases")[0]
    n, e = c["n"], c["e"]
    st = n - e
    manual, auto = n * MANUAL_MIN, e * MANUAL_MIN + st * REVIEW_MIN
    out = {"cases": n, "straight_through": st, "exceptions": e, "pct_straight": round(100 * st / n, 1) if n else 0,
           "manual_minutes": manual, "autopilot_minutes": auto, "minutes_saved": manual - auto,
           "overdue_eur": round(C.q("SELECT coalesce(sum(amount_overdue),0) s FROM cases")[0]["s"], 2)}
    out.update(accuracy())
    return out


def accuracy():
    """Against the bank's gold labels (cases_gold), if present: rules vs gold, model vs gold."""
    try:
        r = C.q("""SELECT count(*) n,
                     avg(CASE WHEN t.rule_decision = g.decision AND coalesce(t.rule_exception,'') = coalesce(g.exception,'') THEN 1 ELSE 0 END) rule_acc,
                     avg(CASE WHEN t.llm_decision IS NULL THEN NULL WHEN t.llm_decision = g.decision AND coalesce(t.llm_exception,'') = coalesce(g.exception,'') THEN 1 ELSE 0 END) llm_acc,
                     count(t.llm_decision) n_llm, any_value(t.model) model
                   FROM triage_log t JOIN cases_gold g USING(case_id)""")[0]
        exc_gold = C.q("""SELECT count(*) FILTER (WHERE g.exception IS NOT NULL) ge,
                             count(*) FILTER (WHERE g.exception IS NOT NULL AND k.status IN ('exception','held')) caught
                          FROM cases_gold g JOIN cases k USING(case_id)""")[0]
        return {"gold_n": r["n"], "rule_accuracy": round(100 * (r["rule_acc"] or 0), 1),
                "model_accuracy": None if r["llm_acc"] is None else round(100 * r["llm_acc"], 1), "model_cases": r["n_llm"],
                "model": (r["model"] or "").split(" (")[0], "exceptions_caught": f"{exc_gold['caught']}/{exc_gold['ge']}"}
    except Exception:
        return {}


def decide_action(action_id, decision, actor, role):
    if decision == "approved" and action_id.startswith("A-REQ"):   # four-eyes: a chat request can't be approved by the person who asked
        req = C.q("SELECT actor FROM audit WHERE event='action_proposed' AND object_id=? ORDER BY ts LIMIT 1", [action_id])
        if req and req[0]["actor"] == actor:
            C.audit(actor, role, "four_eyes_blocked", action_id, {"rule": "requester cannot approve own request"})
            return False
    a = C.q("SELECT * FROM actions WHERE action_id=?", [action_id])
    if not a:
        return
    a = a[0]
    if a["status"] != "proposed":
        return
    if decision == "approved":
        C.x("UPDATE actions SET status='executed', approved_by=?, ts=now() WHERE action_id=?", [f"{actor} ({role})", action_id])
        what = {"send_reminder": "message sent (mock: nothing really leaves the demo)", "post_late_fee": "late fee posted (mock)",
                "escalate": "case handed over (mock)", "draft_email": "email sent (mock)"}.get(a["kind"], "executed (mock)")
        C.audit(actor, role, "action_approved", action_id, {"kind": a["kind"], "case": a["case_id"]})
        from autopilot import outbox
        letter, batch = outbox.write(a, actor, role)
        what = (f"letter written to outbox/{letter}; " if letter else "") + f"row added to outbox/{batch} (ready for the PEC gateway / core banking)"
        C.audit("executor", "system", "action_executed", action_id, {"result": what, "outbox": [x for x in (letter, batch) if x], "approved_by": f"{actor} ({role})"})
        if a["case_id"] and not C.q("SELECT 1 FROM actions WHERE case_id=? AND status='proposed'", [a["case_id"]]):
            C.x("UPDATE cases SET status='done' WHERE case_id=? AND status='awaiting_approval'", [a["case_id"]])
    else:
        C.x("UPDATE actions SET status='rejected', approved_by=?, ts=now() WHERE action_id=?", [f"{actor} ({role})", action_id])
        C.audit(actor, role, "action_rejected", action_id, {"kind": a["kind"], "case": a["case_id"]})


def approve_all_straight(actor, role):
    ids = [r["action_id"] for r in C.q("SELECT action_id FROM actions WHERE status='proposed' AND proposed_by='autopilot'")]
    for i in ids:
        decide_action(i, "approved", actor, role)
    C.audit(actor, role, "batch_approved", None, {"actions": len(ids)})
    return len(ids)


def resolve_exception(case_id, decision, actor, role):
    """Human decision on a stopped case: 'hold' (no action) or 'proceed' (propose the standard reminder for approval)."""
    C.x("UPDATE cases SET status=? WHERE case_id=?", ["held" if decision == "hold" else "awaiting_approval", case_id])
    C.audit(actor, role, f"exception_{decision}", case_id, {})
    if decision == "proceed":
        c = C.q("SELECT k.*, l.pseudonym AS loan_ps FROM cases k LEFT JOIN loans l USING(loan_id) WHERE case_id=?", [case_id])[0]
        ch = "email" if c["bucket"] == "1-30" else "PEC"
        case = {"customer": c["customer_id"], "loan": c.get("loan_ps") or c["loan_id"], "days_past_due": c["days_past_due"], "amount_overdue": c["amount_overdue"]}
        C.x("INSERT INTO actions VALUES (?, 'send_reminder', ?, ?, 'proposed', 'autopilot', NULL, now())",
            [f"A-{case_id}-H", case_id, json.dumps({"channel": ch, "to": case["customer"], "body": letter(case, ch), "note": "after human review of exception"}, ensure_ascii=False)])
