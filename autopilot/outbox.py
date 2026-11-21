"""Finished output of the reminder autopilot. Written ONLY when a person approves an action.

runs/outbox/letters/<action_id>.txt        the actual reminder letter / PEC message, addressed to the real customer
runs/outbox/pec_gateway_batch_<date>.csv   one row per approved send/fee/escalation, ready to hand to the PEC gateway / core banking
The outbox is the bank's egress point: pseudonyms are resolved to real names/addresses here, after approval, by an
authorised (credit) role. Nothing in this folder exists before approval.
"""
import csv, json, os, re, datetime as dt
from brain import core as C

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = __import__("os").environ.get("OUTBOX") or os.path.join(ROOT, "runs", "outbox")
FIELDS = ["action_id", "case_id", "kind", "channel", "recipient_name", "recipient_address", "loan_id", "amount_overdue_eur", "fee_eur",
          "escalate_to", "approved_by", "approved_at", "letter_file"]


def _real(text):
    v = C.vault()
    return re.sub(r"<([A-Z][A-Z_]*_\d+)>", lambda m: (v.get(m.group(1)) or (None, m.group(0)))[1], text or "")


def clear():
    if os.path.isdir(OUT):
        for root, _, files in os.walk(OUT):
            for f in files: os.remove(os.path.join(root, f))


def files():
    if not os.path.isdir(OUT): return []
    out = []
    for root, _, fs in os.walk(OUT):
        for f in sorted(fs):
            p = os.path.join(root, f); out.append({"name": os.path.relpath(p, OUT), "bytes": os.path.getsize(p), "mtime": dt.datetime.fromtimestamp(os.path.getmtime(p))})
    return sorted(out, key=lambda x: x["name"])


def write(action, actor, role):
    """Called after approval. Returns the relative path of the letter (if any)."""
    p = json.loads(action["payload"]) if isinstance(action["payload"], str) else (action["payload"] or {})
    case = (C.q("SELECT k.*, c.full_name, c.email, c.address FROM cases k LEFT JOIN customers c ON c.pseudonym = k.customer_id WHERE case_id=?",
                [action["case_id"]]) or [{}])[0] if action["case_id"] else {}
    name = case.get("full_name") or _real(p.get("to", ""))
    addr = case.get("email") or ""
    now = dt.datetime.now()
    os.makedirs(os.path.join(OUT, "letters"), exist_ok=True)
    letter_rel = ""
    if action["kind"] in ("send_reminder", "draft_email"):
        channel = p.get("channel", "email")
        body = _real(p.get("body", ""))
        subj = p.get("subject") or ("Formal notice of overdue payment (PEC)" if channel == "PEC" else "Reminder: overdue instalment")
        letter_rel = f"letters/{action['action_id']}.txt"
        with open(os.path.join(OUT, letter_rel), "w") as f:
            f.write(f"From: Lumen Bank - Credit Department <crediti@pec.lumenbank.example>\nTo: {name} <{addr or 'address on file'}>\n"
                    f"Channel: {channel}\nSubject: {subj}\nDate: {now:%d/%m/%Y %H:%M}\nApproved by: {actor} ({C.ROLES[role]['label']})\n"
                    f"Reference: {action['action_id']} / {action['case_id'] or '-'}\n\n{body}\n\n"
                    f"-- This message was prepared with the help of an AI system and reviewed and approved by a Lumen Bank employee before sending.\n")
    batch = os.path.join(OUT, f"pec_gateway_batch_{now:%Y%m%d}.csv")
    new = not os.path.exists(batch)
    with open(batch, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new: w.writeheader()
        w.writerow({"action_id": action["action_id"], "case_id": action["case_id"] or "", "kind": action["kind"], "channel": p.get("channel", ""),
                    "recipient_name": name, "recipient_address": addr, "loan_id": case.get("loan_id", ""),
                    "amount_overdue_eur": f"{case['amount_overdue']:.2f}" if case.get("amount_overdue") is not None else "",
                    "fee_eur": p.get("amount_eur", "") if action["kind"] == "post_late_fee" else "", "escalate_to": p.get("to", "") if action["kind"] == "escalate" else "",
                    "approved_by": f"{actor} ({role})", "approved_at": now.isoformat(timespec="seconds"), "letter_file": letter_rel})
    return letter_rel, os.path.relpath(batch, OUT)
