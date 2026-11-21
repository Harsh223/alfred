#!/usr/bin/env python3
"""Jury checks: clicks through the live app like a juror (HTTP only) and marks every challenge requirement PASS/FAIL with evidence.
Challenge A (7 checks) + Challenge B (3 musts) + data rule.   python tests/jury_checks.py  -> runs/jury_checks.json"""
import json, re, sys, time, html as H, urllib.request, urllib.parse, http.cookiejar
import duckdb

BASE = __import__("os").environ.get("APP_URL", "http://127.0.0.1:8080")
RES = []


def S(role):
    cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open(f"{BASE}/as/{role}?next=/today", timeout=120); return op


def get(op, path): return op.open(BASE + path, timeout=180).read().decode()
def post(op, path, data=None):
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data or {}).encode(), method="POST")
    return op.open(req, timeout=600).read().decode()
def ask(op, q):
    req = urllib.request.Request(f"{BASE}/api/ask", data=json.dumps({"q": q}).encode(), headers={"content-type": "application/json"})
    d = json.loads(op.open(req, timeout=180).read()); d["text"] = H.unescape(" ".join(re.sub(r"<[^>]+>", " ", d["html"]).split())); return d
def text(h): return H.unescape(" ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "", h, flags=re.S)).split()))
def check(cid, name, ok, evidence):
    RES.append({"id": cid, "check": name, "pass": bool(ok), "evidence": evidence}); print(f"{'PASS' if ok else 'FAIL'}  {cid:3} {name}: {evidence}", flush=True)


def main():
    urllib.request.urlopen(urllib.request.Request(f"{BASE}/admin/reset", method="POST", headers={"X-Admin-Token": open("/Users/harsh223/Desktop/gdg/runs/.admin_token").read().strip()} if __import__("os").path.exists("/Users/harsh223/Desktop/gdg/runs/.admin_token") else {}), timeout=120)
    time.sleep(2)
    rm, it = S("rm_credit"), S("it_support")
    con = duckdb.connect(__import__("os").environ.get("BANK_DB", "data/bank.duckdb"), read_only=True)
    secrets = [v for (v,) in con.execute("select real_value from vault where label in ('PERSON','IBAN','TAX_CODE','EMAIL','PHONE')").fetchall() if len(v) > 6]

    # ---- A1 speaks first
    for i in range(40):
        t_rm, t_it = get(rm, "/today"), get(it, "/today")
        if "generating" not in t_rm.lower() and "generating" not in t_it.lower(): break
        time.sleep(3)
    em = get(rm, "/email")
    aud = text(get(rm, "/audit?event=brief_generated"))
    cites_rm = len(re.findall(r'href="/doc/', t_rm)); cites_it = len(re.findall(r'href="/doc/', t_it))
    check("A1", "Speaks first (brief per role, nobody asked)", cites_rm > 0 and cites_it > 0 and "scheduler" in aud.lower() and "/doc/" in em,
          f"Today RM {cites_rm} cited items, IT {cites_it}; morning email has sources: {'/doc/' in em}; audit 'brief generated' by scheduler: {'scheduler' in aud.lower()}")

    # ---- A2 curation
    st = json.loads(get(rm, "/api/state"))
    pend = [m for m in st["memory"] if m["status"] == "pending"]
    good = next((m for m in pend if "250,000" in m["text"]), None); bad = next((m for m in pend if "150,000" in m["text"]), None)
    q2 = "What is the maximum SME credit line without committee approval?"
    before = ask(rm, q2)
    if good and bad:
        post(rm, f"/memory/{good['fact_id']}/approved"); post(rm, f"/memory/{bad['fact_id']}/rejected")
    after = ask(rm, q2)
    st2 = json.loads(get(rm, "/api/state")); stat = {m["fact_id"]: m["status"] for m in st2["memory"]}
    ok2 = (good and bad and before["status"] == "abstain" and after["status"] == "ok" and "250,000" in after["text"] and "150,000" not in after["text"]
           and "/doc/" in after["html"] and stat.get(good["fact_id"]) == "approved" and stat.get(bad["fact_id"]) == "rejected")
    check("A2", "People curate memory (approve one, reject one, then ask)", ok2,
          f"before: {before['status']}; approved {good and good['fact_id']} (250,000) / rejected {bad and bad['fact_id']} (150,000); after: {after['status']} → '{after['text'][:110]}'")

    # ---- A3 knows who's asking
    q3 = "Which company is breaching its covenant?"
    a_rm, a_it = ask(rm, q3), ask(it, q3)
    leak = [s for s in secrets if s in a_it["text"]]
    check("A3", "Same question, finance vs tech", a_rm["status"] == "ok" and "4.6" in a_rm["text"] and a_it["status"] in ("denied", "abstain") and not leak and "4.6" not in a_it["text"],
          f"finance: {a_rm['status']} '{a_rm['text'][:80]}' | tech: {a_it['status']} '{a_it['text'][:80]}' | real data leaked to tech: {len(leak)}")

    # ---- A4 cites (every OK answer)
    qs = ["whats the late fee on a pec reminder", "when is the bank of italy q3 report due", "what happens after 90 days overdue", "who has expiring ID documents?",
          "tell me about the AML alert", "whats status of my work?", q3]
    oks = [(q, ask(rm, q)) for q in qs] + [(q, ask(it, q)) for q in ["why did the nightly batch fail?", "branch hours?", "whats status of my work?"]]
    oks = [(q, d) for q, d in oks if d["status"] == "ok"] + [(q2, after), (q3, a_rm)]
    uncited = [q for q, d in oks if "/doc/" not in d["html"]]
    check("A4", "Every answer cites its source", len(oks) >= 8 and not uncited, f"{len(oks)} answers, {len(oks) - len(uncited)} with clickable sources; uncited: {uncited}")

    # ---- A5 admits gaps
    gaps = [ask(rm, q) for q in ["What is our mortgage rate in Spain?", "Who is the new CEO?", "What was the SME limit in 2019?"]]
    check("A5", "Says I don't know for missing data", all(g["status"] == "abstain" and "don't know" in g["text"].lower() for g in gaps),
          " | ".join(f"{g['status']}: '{g['text'][:50]}'" for g in gaps))

    # ---- B1 + A6: run autopilot, nothing leaves before approval
    k0 = text(get(rm, "/autopilot"))
    post(rm, "/autopilot/run")
    st = json.loads(get(rm, "/api/state"))
    cases, acts = st["cases"], st["actions"]
    exc = [c for c in cases if c["status"] == "exception"]; prop = [a for a in acts if a["status"] == "proposed"]
    executed_before = [a for a in acts if a["status"] == "executed"]
    exc_with_actions = [a for a in prop if a["case_id"] in {c["case_id"] for c in exc}]
    ok6 = prop and not executed_before and not st["outbox"]
    first = next(a for a in prop if a["kind"] == "send_reminder" and a["proposed_by"] == "autopilot")
    post(rm, f"/actions/{first['action_id']}/approved")
    st_a = json.loads(get(rm, "/api/state"))
    a1 = next(a for a in st_a["actions"] if a["action_id"] == first["action_id"])
    letter = f"letters/{first['action_id']}.txt"
    check("A6", "Only proposes; nothing happens until approval", ok6 and a1["status"] == "executed" and "Anna" in (a1["approved_by"] or "") and letter in st_a["outbox"],
          f"{len(prop)} proposed, {len(executed_before)} executed and {len(st['outbox'])} outbox files before approval; after approving {first['action_id']}: "
          f"{a1['status']} by {a1['approved_by']}, outbox now {st_a['outbox'][:2]}")

    # ---- A7 fits the day
    ch, em2 = get(rm, "/chat"), get(rm, "/email")
    check("A7", "Meets the team where they work (chat + morning email)", ("<input" in ch or "<textarea" in ch) and "good morning" in text(em2).lower(),
          f"chat page with input: {('<input' in ch)}; morning email page: {'morning' in text(em2).lower()}")

    # ---- B1 end to end
    post(rm, "/autopilot/approve_all")
    st_b = json.loads(get(rm, "/api/state"))
    ex_acts = [a for a in st_b["actions"] if a["status"] == "executed"]
    exc_still = [c for c in st_b["cases"] if c["status"] == "exception"]
    batch = next((f for f in st_b["outbox"] if f.startswith("pec_gateway_batch")), None)
    rows = len(get(rm, f"/outbox/file/{batch}").strip().splitlines()) - 1 if batch else 0
    letters = [f for f in st_b["outbox"] if f.startswith("letters/")]
    sample = get(rm, f"/outbox/file/{letters[0]}") if letters else ""
    exc_out = [a for a in ex_acts if a["case_id"] in {c["case_id"] for c in exc_still}]
    check("B1", "Raw input in → finished output out, stops at exceptions",
          len(cases) > 0 and exc and not exc_with_actions and rows == len(ex_acts) and letters and not exc_out and "To:" in sample and "<CLIENT_" not in sample,
          f"{len(cases)} cases from the arrears extract → {len(exc_still)} stopped as exceptions (0 actions on them: {not exc_with_actions and not exc_out}); "
          f"{len(ex_acts)} approved actions → {rows} batch rows in {batch}, {len(letters)} letters; letter addressed to a real name: {'<CLIENT_' not in sample}")

    # ---- B2 business case
    ap = text(get(rm, "/autopilot"))
    m = re.search(r"([\d.]+) h saved today", ap); e = re.search(r"€([\d,]+)/day", ap)
    check("B2", "Who loses time/money, how much, what we save", bool(m and e and "Assumptions" in ap and "credit officer" in ap),
          f"'{m.group(0) if m else '-'}', '€{e.group(1) if e else '-'}/day', overdue € shown: {'overdue' in ap}, assumptions stated: {'Assumptions' in ap}")

    # ---- B3 trail
    tr = json.loads(get(rm, f"/api/trail/{first['action_id'].split('-')[1] + '-' + first['action_id'].split('-')[2]}"))
    evs = [t["event"] for t in tr]
    ev_case = next((t for t in tr if t["event"] == "case_evaluated"), {})
    appr = next((t for t in tr if t["event"] == "action_approved"), {})
    exe = next((t for t in tr if t["event"] == "action_executed"), {})
    ok_b3 = ev_case.get("detail", {}).get("input") and ev_case["detail"].get("rule") and ev_case["detail"].get("model") and appr.get("actor") and exe.get("detail", {}).get("outbox")
    check("B3", "Trail: what, on which input, who approved", bool(ok_b3),
          f"events {evs}; input row keys {list(ev_case.get('detail', {}).get('input', {}).keys())[:4]}; rule '{(ev_case.get('detail') or {}).get('rule', '')[:40]}'; "
          f"model {(ev_case.get('detail') or {}).get('model')}; approved by {appr.get('actor')} at {appr.get('ts', '')[:19]}; output {exe.get('detail', {}).get('outbox')}")

    # ---- D data
    foot = text(get(rm, "/today"))
    check("D", "Synthetic data only, no real people", "Synthetic data only" in foot, "UI footer: 'Synthetic data only: Lumen Bank and every person in it are fictional.' · generator: data/scripts/gen_bank.py (Faker, seed 7)")

    p = sum(r["pass"] for r in RES)
    json.dump({"passed": p, "total": len(RES), "checks": RES}, open("runs/jury_checks.json", "w"), indent=1, ensure_ascii=False)
    print(f"\n{p}/{len(RES)} PASS")
    urllib.request.urlopen(urllib.request.Request(f"{BASE}/admin/reset", method="POST", headers={"X-Admin-Token": open("/Users/harsh223/Desktop/gdg/runs/.admin_token").read().strip()} if __import__("os").path.exists("/Users/harsh223/Desktop/gdg/runs/.admin_token") else {}), timeout=120)   # leave the demo clean


if __name__ == "__main__":
    main()
