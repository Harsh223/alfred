"""Public metrics dashboard (/dashboard): no login, aggregates only, no personal data. Inline SVG, no external JS. Refreshes every 30 s."""
import html, time
from app.ui import CSS

# status palette (dataviz reference instance; validated on the dark surface): complied = critical, partial = serious
C_COMPLIED, C_PARTIAL = "#d03b3b", "#ec835a"
CAT_LABEL = {"aml_tipping_off": "AML tipping-off", "borderline": "Borderline", "hallucination_bait": "Hallucination bait",
             "indirect_injection": "Indirect injection", "jailbreak": "Jailbreak", "pii_exfiltration": "PII exfiltration",
             "policy_confusion": "Policy confusion", "prompt_injection": "Prompt injection", "role_escalation": "Role escalation",
             "unauthorised_action": "Unauthorised action"}
DS_LABEL = {"bank_heldout": "Bank docs, held out", "hard": "Bank docs, hard variants", "gretel_ood": "Gretel finance (out of distribution)",
            "nemotron_finance": "Nemotron finance (OOD)", "ai4privacy_it": "ai4privacy Italian (OOD)", "ai4privacy_en": "ai4privacy English (OOD)"}
PII_COLS = [("Base GLiNER", ("gliner_base",)), ("Ours: fine-tuned + rules", ("gliner_finetuned+rules", "ours_finetuned+rules", "ours_ft+rules")),
            ("OpenAI privacy-filter", ("openai_privacy_filter",)), ("Ours + privacy-filter", ("ours+privacy_filter", "ours+privacy_filter_ensemble", "ensemble_no_dates"))]

DCSS = """
body{background:var(--bg)}
.db{max-width:1180px;margin:0 auto;padding:28px 16px 80px}
.dh{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px 24px;margin-bottom:28px}
.dh .brand{display:flex;align-items:center;gap:12px}.dh .mk{width:34px;height:34px;border-radius:9px;background:#ececef;color:#0b0c0e;display:grid;place-items:center;font-weight:750}
.dh h1{font-size:24px}.dh .sub{margin-top:4px}.dh .live{margin-left:auto;display:flex;align-items:center;gap:8px;color:var(--mute);font-size:12.5px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px var(--ok-bg)}.dot.off{background:var(--warn);box-shadow:0 0 0 3px var(--warn-bg)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:var(--shadow);min-width:0}
.tile .l{font-size:12.5px;color:var(--mute);font-weight:500}.tile .v{font-size:28px;font-weight:650;letter-spacing:-.6px;margin-top:4px;font-variant-numeric:tabular-nums}
.tile .v small{font-size:15px;color:var(--mute);font-weight:500;margin-left:2px}.tile .d{font-size:12.5px;color:var(--ink2);margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.st{display:inline-flex;align-items:center;gap:5px;font-weight:550}.st.ok{color:var(--ok)}.st.warn{color:var(--warn)}.st.bad{color:var(--bad)}
.st i{font-style:normal;font-size:11px}
.sech{display:flex;align-items:baseline;gap:10px;margin:40px 0 12px;flex-wrap:wrap}.sech h2{font-size:16px}.sech .hint{color:var(--mute);font-size:13px}
.box{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:18px 20px;min-width:0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);margin-bottom:10px}.legend span{display:inline-flex;align-items:center;gap:6px}
.legend b{width:10px;height:10px;border-radius:3px;display:inline-block}
.chart{overflow-x:auto}.chart svg{width:100%;min-width:600px;height:auto;display:block}.chart text{font-family:var(--font)}
.chart .bar:hover{opacity:.8}
.tw{overflow-x:auto}.dt{width:100%;border-collapse:collapse;font-size:13px}.dt th{text-align:left;color:var(--mute);font-weight:500;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
.dt td{padding:9px 10px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;white-space:nowrap}.dt td.n,.dt th.n{text-align:right}
.dt tr:last-child td{border-bottom:0}.dt .best{color:var(--ink);font-weight:650}.dt .ours{background:var(--accent-bg)}
.kv{display:grid;grid-template-columns:1fr auto;gap:8px 16px;font-size:13.5px}.kv div:nth-child(odd){color:var(--ink2)}.kv div:nth-child(even){text-align:right;font-variant-numeric:tabular-nums;font-weight:550}
details.tv{margin-top:10px}details.tv summary{cursor:pointer;color:var(--mute);font-size:12.5px}
.foot{margin-top:48px;color:var(--mute);font-size:12.5px;line-height:1.6}
"""


def _e(x):
    return html.escape(str(x))


def _pct(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f}%"


def _st(ok, label):
    tone, ic = ("ok", "✓") if ok else ("bad", "✕")
    return f'<span class="st {tone}"><i aria-hidden="true">{ic}</i>{_e(label)}</span>'


def _tile(label, value, detail="", unit=""):
    return f'<div class="tile"><div class="l">{_e(label)}</div><div class="v">{value}{f"<small>{unit}</small>" if unit else ""}</div><div class="d">{detail}</div></div>'


def _suite_tile(label, s, what):
    if not s or s.get("total") is None:
        return _tile(label, "–", '<span class="muted">Not run yet</span>')
    ok = s.get("passed") == s.get("total")
    return _tile(label, f'{s["passed"]}<small>/ {s["total"]}</small>', _st(ok, "All passing" if ok else f'{s["total"] - s["passed"]} failing') + f'<span class="muted">{_e(what)}</span>')


def _round_tiles(rounds):
    out = []
    for r in rounds:
        if r.get("status") != "complete":
            out.append(_tile(f'Arena round {r["round"]}', "…", '<span class="st warn"><i aria-hidden="true">◷</i>Running</span><span class="muted">Report appears when done</span>'))
            continue
        leaks, ua = r.get("real_data_leaks"), r.get("unauthorised_actions")
        det = (_st(leaks == 0, f"{leaks} real-data leaks") + _st(ua == 0, f"{ua} unauthorised actions")
               + f'<span class="muted">{r.get("attacks") or 0:,} attacks · {_pct(r.get("attack_success_or_partial_rate"))} incl. partial</span>')
        out.append(_tile(f'Arena round {r["round"]} · attack success', _pct(r.get("attack_success_rate"), 2), det))
    return "".join(out)


def _chart(rounds):
    done = [r for r in rounds if r.get("status") == "complete" and r.get("per_category")]
    if not done:
        return '<div class="muted">No arena report yet.</div>'
    cats = sorted({c for r in done for c in r["per_category"]}, key=lambda c: CAT_LABEL.get(c, c))
    mx = max([0.05] + [(r["per_category"].get(c) or {}).get("success_or_partial_rate") or 0 for r in done for c in cats])
    mx = min(1.0, (int(mx * 20) + 1) / 20)          # round the axis up to the next 5 %
    W, LW, RW, BH, G, GG = 760, 170, 70, 12, 3, 14  # width, label column, value column, bar height, bar gap, group gap
    PW = W - LW - RW
    gh = len(done) * (BH + G) - G
    H = 28 + len(cats) * (gh + GG)
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Attack success rate per red-team category and round">']
    for t in range(0, 101, 5):                       # recessive grid every 5 %, labels every 10 %
        v = t / 100
        if v > mx + 1e-9:
            break
        x = LW + PW * v / mx
        p.append(f'<line x1="{x:.1f}" y1="18" x2="{x:.1f}" y2="{H - 6}" stroke="var(--line)" stroke-width="1"/>')
        if t % 10 == 0 or mx <= 0.1:
            p.append(f'<text x="{x:.1f}" y="12" fill="var(--mute)" font-size="11" text-anchor="middle">{t}%</text>')
    y = 28
    for c in cats:
        p.append(f'<text x="0" y="{y + gh / 2 + 4:.1f}" fill="var(--ink2)" font-size="12.5">{_e(CAT_LABEL.get(c, c))}</text>')
        for r in done:
            d = r["per_category"].get(c) or {}
            n = d.get("n") or 0
            comp = (d.get("complied") or 0) / n if n else 0
            part = (d.get("partial") or 0) / n if n else 0
            p.append(f'<text x="{LW - 8}" y="{y + BH - 2}" fill="var(--mute)" font-size="10.5" text-anchor="end">R{r["round"]}</text>')
            x0 = LW
            tip = f'{CAT_LABEL.get(c, c)} · round {r["round"]}: {d.get("complied") or 0} complied, {d.get("partial") or 0} partial of {n}'
            for val, col in ((comp, C_COMPLIED), (part, C_PARTIAL)):
                w = PW * val / mx
                if w > 0:
                    w = max(w, 2)
                    p.append(f'<rect class="bar" x="{x0:.1f}" y="{y}" width="{w:.1f}" height="{BH}" rx="3" fill="{col}"><title>{_e(tip)}</title></rect>')
                    x0 += w + 2
            if x0 == LW:   # zero: a hairline at the baseline so the row is visibly measured, not missing
                p.append(f'<rect x="{LW}" y="{y}" width="1.5" height="{BH}" fill="var(--faint)"><title>{_e(tip)}</title></rect>')
            p.append(f'<rect x="{LW}" y="{y - 1}" width="{PW}" height="{BH + 2}" fill="transparent"><title>{_e(tip)}</title></rect>')
            p.append(f'<text x="{W - 4}" y="{y + BH - 2}" fill="{"var(--ink)" if comp + part else "var(--mute)"}" font-size="11" text-anchor="end">{_pct(comp + part)}</text>')
            y += BH + G
        y += GG - G
    p.append("</svg>")
    rows = "".join(f'<tr><td>{_e(CAT_LABEL.get(c, c))}</td>' + "".join(
        f'<td class="n">{_pct((r["per_category"].get(c) or {}).get("attack_success_rate"))}</td><td class="n">{_pct((r["per_category"].get(c) or {}).get("success_or_partial_rate"))}</td>'
        for r in done) + "</tr>" for c in cats)
    hdr = "".join(f'<th class="n">R{r["round"]} complied</th><th class="n">R{r["round"]} incl. partial</th>' for r in done)
    legend = (f'<div class="legend"><span><b style="background:{C_COMPLIED}"></b>Complied (attack succeeded)</span>'
              f'<span><b style="background:{C_PARTIAL}"></b>Partial</span><span class="muted">R1, R2, R3 = arena rounds · value = complied + partial</span></div>')
    return (f'{legend}<div class="chart">{"".join(p)}</div><details class="tv"><summary>Show as table</summary><div class="tw" style="margin-top:8px">'
            f'<table class="dt"><tr><th>Category</th>{hdr}</tr>{rows}</table></div></details>')


def _models(models):
    if not models:
        return '<div class="muted">runs/metrics.json not found.</div>'
    cols = [("base_qwen3.5_9b", "Base Qwen3.5-9B"), ("distilled_9b", "Distilled 9B (ours)"), ("teacher_180b", "Teacher 180B MoE")]
    cols = [c for c in cols if c[0] in models]
    rows = [("Autopilot triage, exact", "triage.exact", True), ("Q&A correct", "qa.ans_correct", True), ("Q&A cited", "qa.ans_cited", True),
            ("Unanswerable → \"I don't know\"", "qa.unans_abstain", True), ("Hallucinated answers", "qa.hallucinated", False),
            ("Fact extraction, key recall", "extract_facts.key_recall", True), ("Latency per call", "latency_s", False)]
    body = ""
    for label, k, hi in rows:
        vals = [models[c][k] for c, _ in cols]
        nums = [v for v in vals if v is not None]
        best = (max(nums) if hi else min(nums)) if nums else None
        cells = "".join(f'<td class="n{" best" if v == best else ""}{" ours" if c == "distilled_9b" else ""}">'
                        f'{"–" if v is None else (f"{v:.2f} s" if k == "latency_s" else _pct(v))}</td>' for (c, _), v in zip(cols, vals))
        body += f"<tr><td>{_e(label)}</td>{cells}</tr>"
    n = next((models[c].get("n") for c, _ in cols if models[c].get("n")), None)
    return (f'<div class="tw"><table class="dt"><tr><th>Held-out tasks{f" (n={n})" if n else ""}</th>'
            + "".join(f'<th class="n">{_e(l)}</th>' for _, l in cols) + f"</tr>{body}</table></div>")


def _pii(pii, ws):
    if not pii:
        return '<div class="muted">No PII evaluation found.</div>'
    order = [d for d in DS_LABEL if d in pii] + [d for d in pii if d not in DS_LABEL]
    body = ""
    for ds in order:
        vals = []
        for _, keys in PII_COLS:
            vals.append(next((pii[ds][k] for k in keys if pii[ds].get(k) is not None), None))
        if all(v is None for v in vals):
            continue
        best = max(v for v in vals if v is not None)
        body += f'<tr><td>{_e(DS_LABEL.get(ds, ds))}</td>' + "".join(
            f'<td class="n{" best" if v == best else ""}{" ours" if i == 1 else ""}">{_pct(v)}</td>' for i, v in enumerate(vals)) + "</tr>"
    note = ""
    if ws and ws.get("workspace_docs"):
        note = (f'<div class="muted small" style="margin-top:10px">Live workspace: {ws["workspace_docs"]} documents, {ws["gold_pii_values"]} PII values, '
                f'<b style="color:var(--ink)">{ws["leaked_values"]} leaked</b>. Recall = share of PII characters masked. In-distribution scores use our own generator; OOD rows are the honest number for unfamiliar formats.</div>')
    return (f'<div class="tw"><table class="dt"><tr><th>Dataset</th>' + "".join(f'<th class="n">{_e(l)}</th>' for l, _ in PII_COLS)
            + f"</tr>{body}</table></div>{note}")


def _autopilot(live, ev):
    src = live if live and live.get("cases") else None
    if src:
        cases, st, ex = src["cases"], src["straight_through"], src["exceptions"]
        manual, auto = src["manual_minutes"] / 60, src["autopilot_minutes"] / 60
        origin = "Live, from the last autopilot run"
    elif ev and ev.get("overdue_cases"):
        cases, st, ex = ev["overdue_cases"], ev["straight_through"], ev["exceptions_stopped"]
        manual, auto = cases * 12 / 60, (ex * 12 + st) / 60
        origin = "From the offline evaluation (autopilot not run yet today)"
    else:
        return '<div class="muted">No autopilot data yet.</div>'
    saved = manual - auto
    acc = ""
    if src and src.get("model_accuracy") is not None:
        acc = f'<div>AI triage agreement with gold labels</div><div>{src["model_accuracy"]}%</div><div>Sensitive cases caught</div><div>{_e(src.get("exceptions_caught"))}</div>'
    return (f'<div class="kv"><div>Overdue cases</div><div>{cases}</div><div>Handled straight through</div><div>{st} ({st / cases * 100:.0f}%)</div>'
            f'<div>Stopped for a person</div><div>{ex}</div><div>Manual effort</div><div>{manual:.1f} h</div><div>With the autopilot</div><div>{auto:.1f} h</div>'
            f'<div>Time saved per run</div><div style="color:var(--ok)">{saved:.1f} h ≈ €{saved * 35:,.0f}</div>'
            f'<div>Per year (220 working days)</div><div>≈ €{saved * 35 * 220 / 1000:,.0f}k</div>{acc}</div>'
            f'<div class="muted small" style="margin-top:12px">{origin}. Assumptions: 12 min to check a case by hand, 1 min to approve a prepared one, €35/h loaded staff cost. Every irreversible step still waits for a human approval.</div>')


def _live(health, sec):
    llm = (health or {}).get("llm") or {}
    rows = "".join(f'<div>{_e({"student": "Distilled 9B (serving)", "teacher": "Teacher 180B"}.get(k, k))}</div><div>{_st(v == "configured", "up" if v == "configured" else v)}</div>' for k, v in llm.items())
    if not llm:
        rows = f'<div>Language model</div><div>{_st(False, "offline: safe stub mode")}</div>'
    ck = (health or {}).get("checker")
    rows += f'<div>Independent checker (Qwen3.8-27B)</div><div>{_st(ck == "configured", "up" if ck == "configured" else ck or "–")}</div>'
    s = sec or {}
    srows = (f'<div>Blocked or refused events</div><div>{s.get("blocked_events", "–")}</div><div>Prompt injections refused</div><div>{s.get("prompt_injections", "–")}</div>'
             f'<div>Out-of-role requests denied</div><div>{s.get("access_denied", "–")}</div><div>Four-eyes blocks</div><div>{s.get("four_eyes_blocked", "–")}</div>'
             f'<div>API calls today</div><div>{s.get("api_calls", "–")}</div>')
    return (f'<div class="two"><div class="box"><h2 style="font-size:14px;margin-bottom:12px">Live health</h2><div class="kv">{rows}</div></div>'
            f'<div class="box"><h2 style="font-size:14px;margin-bottom:12px">Security events today</h2><div class="kv">{srows}</div>'
            f'<div class="muted small" style="margin-top:10px">Counted from the audit trail. Details are visible only to signed-in credit and compliance staff.</div></div></div>')


def render(m):
    s = m.get("suites") or {}
    rounds = m.get("redteam_rounds") or []
    llm_on = any(v == "configured" for v in ((m.get("health") or {}).get("llm") or {}).values())
    body = f"""<div class="db">
<div class="dh"><div class="brand"><div class="mk">A</div><div><h1>ALFRED metrics</h1>
<p class="sub">Agentic Ledger For Regulated Enterprise Decisions · Lumen Bank, Turin (fictional). Public view, aggregates only, no personal data.</p></div></div>
<div class="live"><span class="dot {"" if llm_on else "off"}"></span>Updated {time.strftime("%H:%M:%S")} · refreshes every 30 s · <a href="/v1/metrics">JSON</a> · <a href="/arena">Attack ALFRED</a> · <a href="/api/docs">API docs</a></div></div>

<div class="tiles">{_suite_tile("Jury checks", s.get("jury_checks"), "The 7 challenge checks, end to end")}
{_suite_tile("Human question battery", s.get("human_battery"), "Messy real-world phrasing")}
{_suite_tile("HTTP red team", s.get("redteam_http"), "Forged roles, direct POSTs, XSS")}
{_suite_tile("Public API checks", s.get("api_checks"), "Keys, roles, approval, four-eyes")}</div>

<div class="sech"><h2>Red-team arena</h2><span class="hint">A 180B model attacks the live app; the same model judges every answer at temperature 0.</span></div>
<div class="tiles">{_round_tiles(rounds) or _tile("Arena", "–", '<span class="muted">No run yet</span>')}</div>
<div class="box" style="margin-top:12px"><h2 style="font-size:14px;margin-bottom:12px">Attack success by category and round</h2>{_chart(rounds)}</div>

<div class="sech"><h2>Models</h2><span class="hint">Distilled 9B serves the app; the 180B teacher only generated training data.</span></div>
<div class="box">{_models(m.get("models"))}</div>

<div class="sech"><h2>PII recall</h2><span class="hint">Share of personal-data characters masked before any model sees the text.</span></div>
<div class="box">{_pii(m.get("pii_recall"), m.get("workspace_pii"))}</div>

<div class="sech"><h2>Autopilot business case</h2><span class="hint">Overdue-loan reminders</span></div>
<div class="box">{_autopilot(m.get("autopilot_live"), m.get("autopilot_eval"))}</div>

<div class="sech"><h2>Live system</h2></div>
{_live(m.get("health"), m.get("security_today"))}

<div class="foot">Synthetic data only: Lumen Bank and every person in it are fictional. Everything runs on open-weight models on our own GPUs.
Numbers come from runs/*.json and the audit trail; nothing here identifies a person. <a href="/login">Sign in to the app</a></div>
</div>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>ALFRED Metrics</title><style>{CSS}{DCSS}</style></head><body>{body}</body></html>"""
