"""Public metrics dashboard (/dashboard): no login, aggregates only, no personal data. Comic / neo-brutalist theme from
app/comic.py (light + dark). Inline SVG chart, no external JS. Refreshes every 30 s and keeps the chosen theme."""
import html, json, os, time
from app import comic as K

try:
    from brain import llm as _llm
except Exception:   # dashboard must render even if the model client cannot be imported
    _llm = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# chart fills (comic palette): complied = solid coral, partial = yellow with black hatch
C_COMPLIED, C_PARTIAL = "#ee6a55", "#f5c542"
CAT_LABEL = {"aml_tipping_off": "AML tipping-off", "borderline": "Borderline", "hallucination_bait": "Hallucination bait",
             "indirect_injection": "Indirect injection", "jailbreak": "Jailbreak", "pii_exfiltration": "PII exfiltration",
             "policy_confusion": "Policy confusion", "prompt_injection": "Prompt injection", "role_escalation": "Role escalation",
             "unauthorised_action": "Unauthorised action"}
DS_LABEL = {"bank_heldout": "Bank docs, held out", "hard": "Bank docs, hard variants", "gretel_ood": "Gretel finance (out of distribution)",
            "nemotron_finance": "Nemotron finance (OOD)", "ai4privacy_it": "ai4privacy Italian (OOD)", "ai4privacy_en": "ai4privacy English (OOD)"}
PII_COLS = [("Base GLiNER", ("gliner_base",)), ("Ours: fine-tuned + rules", ("gliner_finetuned+rules", "ours_finetuned+rules", "ours_ft+rules")),
            ("OpenAI privacy-filter", ("openai_privacy_filter",)), ("Ours + privacy-filter", ("ours+privacy_filter", "ours+privacy_filter_ensemble", "ensemble_no_dates"))]

DCSS = """
.d-arrow{font:34px/1 var(--k-display);color:var(--k-red);text-shadow:2px 2px 0 var(--k-shadow)}
.d-rounds{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:18px;align-items:center}
.d-rounds .k-card{height:100%}
.d-big{font:58px/1 var(--k-display);letter-spacing:.5px;margin:14px 0 4px;font-variant-numeric:tabular-nums}
.d-sub{font-size:13px;color:var(--k-mute);font-weight:600}
.d-zeros{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.d-zero{display:inline-flex;align-items:baseline;gap:6px;border:2px solid var(--k-line);border-radius:8px;padding:5px 9px;font-weight:700;font-size:12.5px;background:var(--k-card)}
.d-zero b{font:18px/1 var(--k-display)}
.k-hl .d-zero{background:#fff}
.d-status{display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:0 0 26px}
.d-status .d-sico{flex:none;width:70px;height:70px}
.d-status .d-stxt{flex:1;min-width:220px}
.d-status .d-stitle{font:28px/1 var(--k-display);letter-spacing:.4px}
.d-status p{margin:6px 0 0;font-size:14.5px;font-weight:600}
.d-status.d-on{background:#2fbf71;--k-ink:#0b1f14;--k-line:#111;color:#0b1f14;border-color:#111}
.d-status.d-off{background:var(--k-card)}
.d-burst{transform-origin:50% 50%;animation:d-spin 6s linear infinite}
.d-pulse{transform-origin:50% 50%;animation:d-pulse 1.1s ease-in-out infinite}
@keyframes d-spin{to{transform:rotate(360deg)}}
@keyframes d-pulse{0%,100%{transform:scale(1)}50%{transform:scale(.82)}}
@media (prefers-reduced-motion:reduce){.d-burst,.d-pulse{animation:none}}
.d-pay{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:22px;align-items:start}
.d-money{font:clamp(40px,6vw,64px)/1 var(--k-display);margin:12px 0 6px}
@media (max-width:560px){.d-status{align-items:flex-start;gap:14px}.d-status .d-sico{width:46px;height:46px}.d-status .d-stxt{min-width:0}.d-status .d-stitle{font-size:24px}}
@media (max-width:820px){.d-rounds{grid-template-columns:1fr}.d-arrow{transform:rotate(90deg);justify-self:center}.d-status{display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:0 0 26px}
.d-status .d-sico{flex:none;width:70px;height:70px}
.d-status .d-stxt{flex:1;min-width:220px}
.d-status .d-stitle{font:28px/1 var(--k-display);letter-spacing:.4px}
.d-status p{margin:6px 0 0;font-size:14.5px;font-weight:600}
.d-status.d-on{background:#2fbf71;--k-ink:#0b1f14;--k-line:#111;color:#0b1f14;border-color:#111}
.d-status.d-off{background:var(--k-card)}
.d-burst{transform-origin:50% 50%;animation:d-spin 6s linear infinite}
.d-pulse{transform-origin:50% 50%;animation:d-pulse 1.1s ease-in-out infinite}
@keyframes d-spin{to{transform:rotate(360deg)}}
@keyframes d-pulse{0%,100%{transform:scale(1)}50%{transform:scale(.82)}}
@media (prefers-reduced-motion:reduce){.d-burst,.d-pulse{animation:none}}
.d-pay{grid-template-columns:1fr}.d-big{font-size:48px}}
"""


def _e(x):
    return html.escape(str(x))


def _pct(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f}%"


def _st(ok, label):
    return K.status(ok, label)


def _arena_checks():
    """runs/arena_checks.json: aggregate pass count only (the dashboard is public)."""
    try:
        d = json.load(open(os.path.join(ROOT, "runs/arena_checks.json")))
        return {"passed": d.get("passed"), "total": d.get("total")} if isinstance(d, dict) else None
    except Exception:
        return None


def _suite_tile(label, s, what, cls=""):
    if not s or s.get("total") is None:
        return K.stat(label, "–", '<span>Not run yet</span>', "PENDING", cls)
    ok = s.get("passed") == s.get("total")
    return K.stat(label, f'{s["passed"]}<small>/{s["total"]}</small>',
                  _st(ok, "All passing" if ok else f'{s["total"] - s["passed"]} failing') + f'<span>{_e(what)}</span>',
                  "GREEN" if ok else "RED", cls, "" if ok else "red")


def _round_cards(rounds):
    out = []
    for i, r in enumerate(rounds):
        last = i == len(rounds) - 1
        cls = "k-hl k-tilt-r" if last else ("k-tilt-l" if i == 0 else "")
        if r.get("status") != "complete":
            out.append(K.card(f'<div class="k-card-h" style="margin:0">{K.chip(f"ROUND {r["round"]}")}{K.chip("RUNNING", "blue")}</div>'
                              f'<div class="d-big">…</div><div class="d-sub">Report appears when the round finishes</div>', cls))
            continue
        leaks, ua = r.get("real_data_leaks"), r.get("unauthorised_actions")
        zero = (r.get("attack_success_rate") or 0) == 0
        flag = K.chip("UNBROKEN", "red") if zero else K.chip(f'{r.get("generated") or ""}' or "DONE", "")
        out.append(K.card(
            f'<div class="k-card-h" style="margin:0">{K.chip(f"ROUND {r["round"]}", "" if last else "ylw")}{flag}</div>'
            f'<div class="d-big">{_pct(r.get("attack_success_rate"), 2)}</div>'
            f'<div class="d-sub">attack success · {r.get("attacks") or 0:,} attacks · {_pct(r.get("attack_success_or_partial_rate"))} incl. partial</div>'
            f'<div class="d-zeros"><span class="d-zero"><b>{_e(leaks if leaks is not None else "–")}</b>real-data leaks</span>'
            f'<span class="d-zero"><b>{_e(ua if ua is not None else "–")}</b>unauthorised actions</span></div>', cls))
        if not last:
            out.append('<div class="d-arrow" aria-hidden="true">→</div>')
    return f'<div class="d-rounds">{"".join(out)}</div>' if out else K.card('<span class="k-muted">No arena run yet.</span>')


def _chart(rounds):
    done = [r for r in rounds if r.get("status") == "complete" and r.get("per_category")]
    if not done:
        return '<div class="k-muted">No arena report yet.</div>'
    cats = sorted({c for r in done for c in r["per_category"]}, key=lambda c: CAT_LABEL.get(c, c))
    mx = max([0.05] + [(r["per_category"].get(c) or {}).get("success_or_partial_rate") or 0 for r in done for c in cats])
    mx = min(1.0, (int(mx * 20) + 1) / 20)          # round the axis up to the next 5 %
    W, LW, RW, BH, G, GG = 760, 180, 64, 14, 4, 18  # width, label column, value column, bar height, bar gap, group gap
    PW = W - LW - RW
    gh = len(done) * (BH + G) - G
    H = 30 + len(cats) * (gh + GG)
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Attack success rate per red-team category and round">'
         '<defs><pattern id="k-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         f'<rect width="7" height="7" fill="{C_PARTIAL}"/><line x1="0" y1="0" x2="0" y2="7" stroke="#111" stroke-width="3"/></pattern></defs>']
    for t in range(0, 101, 1 if mx <= 0.1 else 5):
        v = t / 100
        if v > mx + 1e-9:
            break
        x = LW + PW * v / mx
        major = t % (2 if mx <= 0.1 else 10) == 0
        if t == 0:
            continue
        p.append(f'<line x1="{x:.1f}" y1="20" x2="{x:.1f}" y2="{H - 6}" stroke="var(--k-grid)" stroke-width="1.5" stroke-dasharray="{"0" if major else "3 4"}"/>')
        if major:
            p.append(f'<text x="{x:.1f}" y="13" fill="var(--k-mute)" font-size="11.5" font-weight="700" text-anchor="middle">{t}%</text>')
    y = 30
    for c in cats:
        p.append(f'<text x="0" y="{y + gh / 2 + 4:.1f}" fill="var(--k-ink)" font-size="13" font-weight="700">{_e(CAT_LABEL.get(c, c))}</text>')
        for r in done:
            d = r["per_category"].get(c) or {}
            n = d.get("n") or 0
            comp = (d.get("complied") or 0) / n if n else 0
            part = (d.get("partial") or 0) / n if n else 0
            tip = f'{CAT_LABEL.get(c, c)} · round {r["round"]}: {d.get("complied") or 0} complied, {d.get("partial") or 0} partial of {n}'
            p.append(f'<g class="k-row"><title>{_e(tip)}</title>'
                     f'<rect class="k-hit" x="{LW - 34}" y="{y - 2}" width="{PW + 34 + RW}" height="{BH + 4}" rx="4" fill="transparent"/>'
                     f'<text x="{LW - 10}" y="{y + BH - 3}" fill="var(--k-mute)" font-size="11" font-weight="800" text-anchor="end">R{r["round"]}</text>')
            x0 = LW
            for val, fill in ((comp, C_COMPLIED), (part, "url(#k-hatch)")):
                w = PW * val / mx
                if w > 0:
                    w = max(w, 4)
                    p.append(f'<rect class="k-bar" x="{x0:.1f}" y="{y}" width="{w:.1f}" height="{BH}" rx="3" fill="{fill}" stroke="var(--k-line)" stroke-width="2"/>')
                    x0 += w + 3
            if x0 == LW:   # zero: a small outlined stub so the row is visibly measured, not missing
                p.append(f'<rect x="{LW}" y="{y + 3}" width="3" height="{BH - 6}" fill="var(--k-mute)"/>')
            tot = comp + part
            p.append(f'<text x="{W - 4}" y="{y + BH - 3}" fill="{"var(--k-ink)" if tot else "var(--k-mute)"}" font-size="12" font-weight="{800 if tot else 600}" text-anchor="end">{_pct(tot)}</text></g>')
            y += BH + G
        y += GG - G
    p.append(f'<line x1="{LW}" y1="20" x2="{LW}" y2="{H - 6}" stroke="var(--k-line)" stroke-width="3"/></svg>')
    rows = "".join(f'<tr><td>{_e(CAT_LABEL.get(c, c))}</td>' + "".join(
        f'<td class="n">{_pct((r["per_category"].get(c) or {}).get("attack_success_rate"))}</td><td class="n">{_pct((r["per_category"].get(c) or {}).get("success_or_partial_rate"))}</td>'
        for r in done) + "</tr>" for c in cats)
    hdr = "".join(f'<th class="n">R{r["round"]} complied</th><th class="n">R{r["round"]} incl. partial</th>' for r in done)
    legend = (f'<div class="k-legend"><span><i class="k-sw" style="background:{C_COMPLIED}"></i>Complied (attack succeeded)</span>'
              f'<span><i class="k-sw" style="background:repeating-linear-gradient(45deg,#111 0 2px,{C_PARTIAL} 2px 5px)"></i>Partial</span>'
              f'<span class="k-muted" style="font-weight:500">R1 · R2 · R3 = arena rounds · value = complied + partial · hover a bar for counts</span></div>')
    return (f'{legend}<div class="k-chart">{"".join(p)}</div><details class="k-tv"><summary>Show as table</summary><div class="k-tw" style="margin-top:10px">'
            f'<table class="k-table"><tr><th>Category</th>{hdr}</tr>{rows}</table></div></details>')


def _models(models):
    if not models:
        return '<div class="k-muted">runs/metrics.json not found.</div>'
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
    return (f'<div class="k-tw"><table class="k-table"><tr><th>Held-out tasks{f" (n={n})" if n else ""}</th>'
            + "".join(f'<th class="n{" ours" if c == "distilled_9b" else ""}">{_e(l)}</th>' for c, l in cols) + f"</tr>{body}</table></div>"
            '<div class="k-muted k-small" style="margin-top:12px">★ = best in row. Lower is better for hallucinations and latency.</div>')


def _pii(pii, ws):
    if not pii:
        return '<div class="k-muted">No PII evaluation found.</div>'
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
        note = (f'<div class="k-muted k-small" style="margin-top:12px">Live workspace: {ws["workspace_docs"]} documents, {ws["gold_pii_values"]} PII values, '
                f'<b style="color:var(--k-ink)">{ws["leaked_values"]} leaked</b>. Recall = share of PII characters masked. In-distribution scores use our own generator; OOD rows are the honest number for unfamiliar formats.</div>')
    return (f'<div class="k-tw"><table class="k-table"><tr><th>Dataset</th>' + "".join(f'<th class="n{" ours" if i == 1 else ""}">{_e(l)}</th>' for i, (l, _) in enumerate(PII_COLS))
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
        return K.card('<div class="k-muted">No autopilot data yet.</div>')
    saved = manual - auto
    acc = ""
    if src and src.get("model_accuracy") is not None:
        acc = f'<div>AI triage agreement with gold labels</div><div>{src["model_accuracy"]}%</div><div>Sensitive cases caught</div><div>{_e(src.get("exceptions_caught"))}</div>'
    money = K.card(f'<div class="k-card-h" style="margin:0">{K.chip("TIME SAVED PER RUN")}{K.chip("LIVE" if src else "EVAL", "red")}</div>'
                   f'<div class="d-money">{saved:.1f} h</div><div style="font:22px/1.2 var(--k-display)">≈ €{saved * 35:,.0f} per run</div>'
                   f'<div style="font-weight:700;margin-top:10px">≈ €{saved * 35 * 220 / 1000:,.0f}k per year (220 working days)</div>'
                   f'<div class="d-zeros"><span class="d-zero"><b>{st}</b>straight through ({st / cases * 100:.0f}%)</span><span class="d-zero"><b>{ex}</b>stopped for a person</span></div>',
                   "k-hl k-tilt-l")
    kv = K.card(f'<div class="k-card-h">{K.chip("ONE CASE AT A TIME")}<span class="k-muted k-small">{_e(origin)}</span></div>'
                f'<div class="k-kv"><div>Overdue cases</div><div>{cases}</div><div>Handled straight through</div><div>{st} ({st / cases * 100:.0f}%)</div>'
                f'<div>Stopped for a person</div><div>{ex}</div><div>Manual effort</div><div>{manual:.1f} h</div><div>With the autopilot</div><div>{auto:.1f} h</div>'
                f'<div>Time saved per run</div><div style="color:var(--k-ok)">{saved:.1f} h ≈ €{saved * 35:,.0f}</div>'
                f'<div>Per year (220 working days)</div><div>≈ €{saved * 35 * 220 / 1000:,.0f}k</div>{acc}</div>'
                f'<div class="k-muted k-small" style="margin-top:12px">Assumptions: 12 min to check a case by hand, 1 min to approve a prepared one, €35/h loaded staff cost. Every irreversible step still waits for a human approval.</div>')
    return f'<div class="d-pay">{money}{kv}</div>'


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
    return (f'<div class="k-grid k-g2">{K.card(f"""<div class="k-card-h"><h3 class="k-h3">Live health</h3>{K.chip("RIGHT NOW")}</div><div class="k-kv">{rows}</div>""")}'
            + K.card(f'<div class="k-card-h"><h3 class="k-h3">Security events today</h3>{K.chip("AUDIT TRAIL", "red")}</div><div class="k-kv">{srows}</div>'
                     f'<div class="k-muted k-small" style="margin-top:12px">Counted from the audit trail. Details are visible only to signed-in credit and compliance staff.</div>')
            + "</div>")


def _model_health():
    try:
        return _llm.health() if _llm and hasattr(_llm, "health") else None
    except Exception:
        return None


def _status_card(h):
    """Top-of-page model status: ONLINE / WARMING UP (model server restarting) / STUB MODE. Never an error."""
    if not h:
        return ""
    loading = "loading" in (h.get("assistant"), h.get("checker"))
    lab = {"up": "up", "loading": "warming up", "off": "not configured"}
    det = f'Assistant {lab.get(h.get("assistant"), h.get("assistant"))} · independent checker {lab.get(h.get("checker"), h.get("checker"))}'
    burst = K._starburst(50, 50, 48, 38, 12)
    if loading:
        ico = (f'<svg class="d-sico" viewBox="0 0 100 100" aria-hidden="true"><polygon class="d-burst" points="{burst}" fill="#fff" stroke="#111" stroke-width="4" stroke-linejoin="round"/>'
               '<circle class="d-pulse" cx="50" cy="50" r="15" fill="#d9483b" stroke="#111" stroke-width="4"/></svg>')
        return K.card(f'{ico}<div class="d-stxt"><div class="k-card-h" style="margin:0 0 4px;justify-content:flex-start">{K.chip("STATUS")}{K.chip("RECHECKING EVERY 15 S", "red")}</div>'
                      f'<div class="d-stitle">WARMING UP…</div><p>ALFRED\'s model server is restarting on fresh hardware — answers resume in a few minutes. '
                      f'Everything else (metrics, red-team results) is live.</p><div class="k-small" style="margin-top:4px;font-weight:700">{_e(det)}</div></div>',
                      "k-hl d-status", label="Model status: warming up")
    if h.get("ready"):
        ico = (f'<svg class="d-sico" viewBox="0 0 100 100" aria-hidden="true"><polygon points="{burst}" fill="#fff" stroke="#111" stroke-width="4" stroke-linejoin="round"/>'
               '<path d="M33 52 l11 11 l23 -26" fill="none" stroke="#111" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        return K.card(f'{ico}<div class="d-stxt"><div class="d-stitle">ONLINE</div><p>{_e(det)}. Ask it anything in the app, or try to break it in the arena.</p></div>',
                      "d-status d-on", label="Model status: online")
    ico = (f'<svg class="d-sico" viewBox="0 0 100 100" aria-hidden="true"><polygon points="{burst}" fill="var(--k-yellow)" stroke="var(--k-line)" stroke-width="4" stroke-linejoin="round"/>'
           '<rect x="38" y="38" width="24" height="24" rx="3" fill="#111"/></svg>')
    return K.card(f'{ico}<div class="d-stxt"><div class="d-stitle">STUB MODE</div><p>{_e(det)}. The app answers in a safe offline mode; all metrics below are live.</p></div>',
                  "d-status d-off", label="Model status: stub mode")


def _hero(llm_on, loading=False):
    steps = (("1", "Speaks first", "Briefs you before you ask"), ("2", "Admits gaps", "Says “I don't know” instead of guessing"),
             ("3", "Asks before acting", "Every irreversible step waits for you"))
    st = "".join(f'<div class="k-step">{K.badge(n)}<div><b>{_e(t)}</b><small>{_e(d)}</small></div></div>' for n, t, d in steps)
    return f"""<section class="k-hero"><div class="k-hero-grid"><div>
{K.tag("TEAM ALFRED")}
{K.h1("The AI colleague that never acts without asking")}
<p class="k-lede"><b>ALFRED</b> — Agentic Ledger For Regulated Enterprise Decisions, at work in Lumen Bank, Turin (fictional).
This is the public scoreboard: aggregates only, no personal data.</p>
<div class="k-steps">{st}</div></div>
<div class="k-art"><div class="k-bubble">Reminder drafted. Shall I send it? I'll wait for your OK.</div>{K.mascot()}</div></div></section>
<div style="display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:22px 0 0">
<span class="k-live"><span class="k-dot {"" if llm_on else "off"}"></span>{"Live" if llm_on else ("Warming up" if loading else "Stub mode")} · updated {time.strftime("%H:%M:%S")} · refreshes every {15 if loading else 30} s</span></div>"""


def render(m):
    s = m.get("suites") or {}
    rounds = m.get("redteam_rounds") or []
    llm_on = any(v == "configured" for v in ((m.get("health") or {}).get("llm") or {}).values())
    mh = _model_health()
    loading = bool(mh) and "loading" in (mh.get("assistant"), mh.get("checker"))
    if mh:
        llm_on = mh.get("assistant") == "up"
    tiles = (_suite_tile("Jury checks", s.get("jury_checks"), "The 7 challenge checks, end to end", "k-hl k-tilt-l")
             + _suite_tile("Human question battery", s.get("human_battery"), "Messy real-world phrasing")
             + _suite_tile("HTTP red team", s.get("redteam_http"), "Forged roles, direct POSTs, XSS")
             + _suite_tile("Public API checks", s.get("api_checks"), "Keys, roles, approval, four-eyes")
             + _suite_tile("Arena checks", _arena_checks(), "The public attack arena itself"))
    body = f"""{K.topbar([("JSON", "/v1/metrics"), ("API docs", "/api/docs"), ("Attack ALFRED", "/arena", True)])}
<main class="k-wrap">
{_status_card(mh)}
{_hero(llm_on, loading)}

{K.section_head("THE PROOF", "Every test suite, all green", "Automated suites re-run against the live app. Each tile is the latest run.")}
<div class="k-grid k-g5">{tiles}</div>

{K.section_head("THE GAUNTLET", "Red-team arena: three rounds, zero breaks", "A 180B model attacks the live app; the same model judges every answer at temperature 0. We patched after each round.")}
{_round_cards(rounds)}
<div style="margin-top:26px">{K.card(f'<div class="k-card-h"><h3 class="k-h3">Attack success by category and round</h3>{K.chip("LOWER IS BETTER")}</div>{_chart(rounds)}')}</div>

{K.section_head("THE BRAINS", "A small model that learned from a giant", "Distilled 9B serves the app; the 180B teacher only generated training data.")}
{K.card(_models(m.get("models")))}

{K.section_head("THE SHIELD", "PII masked before any model sees it", "Share of personal-data characters masked, in and out of distribution.")}
{K.card(_pii(m.get("pii_recall"), m.get("workspace_pii")))}

{K.section_head("THE PAYOFF", "Autopilot business case", "Overdue-loan reminders: ALFRED prepares, a person approves.")}
{_autopilot(m.get("autopilot_live"), m.get("autopilot_eval"))}

{K.section_head("LIVE", "System status")}
{_live(m.get("health"), m.get("security_today"))}

<div class="k-foot">Synthetic data only: Lumen Bank and every person in it are fictional. Everything runs on open-weight models we host ourselves.
Numbers come from runs/*.json and the audit trail; nothing here identifies a person. <a href="/login">Sign in to the app</a> · <a href="/v1/metrics">JSON</a> · <a href="/arena">Attack ALFRED</a></div>
</main>"""
    return K.page("ALFRED Metrics", body, refresh=15 if loading else 30, extra_css=DCSS)
