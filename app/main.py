"""ALFRED (Lumen Bank) · Company Brain + Reminder Autopilot. Run: .venv/bin/uvicorn app.main:app --port 8080"""
import html, json, os, re, threading, time
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from brain import core as C
from brain import llm
from autopilot import engine as E
from app.ui import page, tag, head, section, empty, panel

app = FastAPI(title="ALFRED API", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")   # /docs is the Sources page
USERS = {"rm_credit": "Anna Ferri", "it_support": "Luca Bruno", "compliance": "Sofia Marino"}   # fictional staff
BRIEF_EVERY_MIN = int(os.environ.get("BRIEF_EVERY_MIN", "30"))


_arena = None   # app.arena when ARENA_MODE is on (installed at the bottom of this file)


def team_of(req):
    """Arena team session (team, role) from the signed cookie, or None for normal demo users."""
    return _arena.session(req) if _arena else None


def arena_locked(req):
    """Public arena: team sessions can't start on-demand autopilot runs or bulk approvals."""
    return bool(team_of(req)) and _arena.public_arena()


def sess(req):
    t = team_of(req)
    if t:                                   # team session: role and identity come from the signed cookie only
        return t[1], _arena.web_actor(t[1], t[0])
    role = req.cookies.get("role")
    return (role, USERS[role]) if role in C.ROLES else (None, None)


def P(req, title, body, active=""):
    role, user = sess(req)
    t = team_of(req)
    pend = C.q("SELECT count(*) n FROM actions WHERE status='proposed'")[0]["n"] if role and C.ROLES[role]["credit"] else 0
    return HTMLResponse(page(title, body, active, user, C.ROLES[role]["label"] if role else None, llm.status(), pend, C.ROLES[role]["credit"] if role else True,
                             team=t[0] if t else None))


def need(req):
    role, user = sess(req)
    if not role:
        raise _Redirect()
    C.NO_REID.set(bool(team_of(req)))       # arena teams never see re-identified customers
    return role, user


def _chat_scope(req, role):
    t = team_of(req)
    return f"{role}|{t[0]}" if t else role   # each arena team has its own chat history


class _Redirect(Exception):
    pass


@app.exception_handler(_Redirect)
async def _to_login(req, exc):
    return RedirectResponse("/login", 303)


# ------------------------------------------------------------------ scheduler: the brain speaks first
def _scheduler():
    while True:
        for r in C.ROLES:
            try:
                C.make_brief(r)
            except Exception as e:
                C.audit("scheduler", r, "brief_failed", None, {"error": str(e)[:200]})
        time.sleep(BRIEF_EVERY_MIN * 60)


@app.on_event("startup")
def _start():
    C.con()
    if not C.latest_brief("rm_credit"):
        for r in C.ROLES:   # synchronous first pass so the brief is already there when anyone logs in
            try: C.make_brief(r)
            except Exception: pass
    threading.Thread(target=lambda: (time.sleep(BRIEF_EVERY_MIN * 60), _scheduler()), daemon=True).start()


# ------------------------------------------------------------------ helpers (display only)
import re
from app.ui import svg


def _locked(title, text=''):
    return f'<div class="wrap narrow" style="margin-top:8vh">{empty("lock", title, text)}</div>'

CITE_A = re.compile(r'<a class="cite" href="/doc/([^"]+)" target="_blank">\1</a>')


def _md(h):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)


def _titles(ids):
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    return {r["doc_id"]: r["title"] for r in C.q(f"SELECT doc_id, title FROM documents WHERE doc_id IN ({ph})", list(ids))}


def _numbered(rendered, order):
    """Turn rendered [DOC-ID] citation links into small numbered chips, in order of first appearance."""
    def sub(m):
        d = m.group(1)
        if d not in order:
            order.append(d)
        return f'<a class="cn" href="/doc/{d}" target="_blank" title="{d}">{order.index(d) + 1}</a>'
    return CITE_A.sub(sub, rendered)


def _first_name(user):
    return user.split()[0]


def _counts(role):
    pa = C.q("SELECT count(*) n FROM actions WHERE status='proposed'")[0]["n"] if C.ROLES[role]["credit"] else 0
    pm = len([x for x in C.memory_list(role) if x["status"] == "pending"])
    cs = C.q("""SELECT count(*) n, count(*) FILTER (WHERE status='exception') e, count(*) FILTER (WHERE status='new') nw,
                count(*) FILTER (WHERE status NOT IN ('exception','held','new')) h FROM cases""")[0] if C.ROLES[role]["credit"] else None
    return pa, pm, cs


# ------------------------------------------------------------------ login
@app.get("/login", response_class=HTMLResponse)
def login(req: Request):
    blurb = {"rm_credit": "Customers, credit and reminders", "it_support": "Systems and IT operations", "compliance": "Regulation, KYC and AML"}
    cards = "".join(f"""<form method="post" action="/login"><input type="hidden" name="role" value="{r}"><button>
        <span class="avatar">{"".join(w[0] for w in USERS[r].split()[:2])}</span><span class="tx"><div class="t">{USERS[r]}</div>
        <div class="muted small">{C.ROLES[r]['label']} · {blurb.get(r, '')}</div></span><span class="chev">{svg('chev')}</span></button></form>""" for r in C.ROLES)
    body = f"""<div class="loginwrap"><div class="lg">L</div><h1 style="font-size:24px">Sign in to Lumen Bank</h1>
    <p class="sub">Choose your account. What you can see depends on your sign-in, never on what you type.</p>
    <div class="login">{cards}</div>
    <div class="notice">{svg('shieldok')}<span>Runs on the bank's own servers. Synthetic data only: Lumen Bank and every person in it are fictional.</span></div>
    <p class="muted small" style="text-align:center;margin-top:18px"><a href="/dashboard">Public metrics dashboard</a> · <a href="/arena">Attack ALFRED</a> · <a href="/api/docs">API docs</a></p></div>"""
    return HTMLResponse(page("Sign in", body))


@app.post("/login")
def do_login(role: str = Form(...)):
    r = RedirectResponse("/today", 303)
    r.delete_cookie("arena")
    if role in C.ROLES:
        r.set_cookie("role", role, httponly=True, samesite="lax")
        C.audit(USERS[role], role, "login", None, {})
    return r


@app.get("/as/{role}")
def login_as(role: str, next: str = "/today"):
    """One-click demo login (same effect as the login page)."""
    r = RedirectResponse(next if next.startswith("/") else "/today", 303)
    r.delete_cookie("arena")
    if role in C.ROLES:
        r.set_cookie("role", role, httponly=True, samesite="lax")
        C.audit(USERS[role], role, "login", None, {})
    return r


@app.get("/logout")
def logout():
    r = RedirectResponse("/login", 303); r.delete_cookie("role"); r.delete_cookie("arena"); return r


@app.get("/")
def root(req: Request):
    return RedirectResponse("/today" if sess(req)[0] else "/login", 303)


# ------------------------------------------------------------------ today (the brain speaks first)
def _icon_for(t):
    t = t.lower()
    for keys, ic, tone in ((("suspicious", "injection", "blocked"), "alert", "bad"), (("covenant", "ebitda"), "trend", "warn"),
                           (("aml", "money", "transfers"), "shield", "bad"), (("kyc", "identity", "id document", "id doc"), "id", "warn"),
                           (("deadline", "report", "due by", "submit"), "cal", ""), (("batch", "server", "job", "record error"), "server", ""),
                           (("autopilot", "overdue", "reminder"), "/autopilot", ""), (("approval", "approve"), "/actions", "ok"),
                           (("fact", "memory"), "/memory", ""), (("incident", "outage", "down"), "alert", "warn"),
                           (("data quality", "duplicate", "records", "correction"), "/docs", "")):
        if any(k in t for k in keys):
            return ic, tone
    return "spark", "info"


def _brief_items(text):
    items = []
    for line in (text or "").splitlines():
        l = line.strip()
        if not re.match(r"^([*•\-]|\d+\.)\s+", l):
            continue
        l = re.sub(r"^([*•\-]|\d+\.)\s+", "", l)
        cites = re.findall(r"\[([A-Z]{2,4}-[0-9A-Za-z\-]+)\]", l)
        body = re.sub(r"\s*\[[A-Z]{2,12}\]", "", l)                     # drop non-document tags like [AUTOPILOT]
        body = body.strip()
        m = re.match(r"\*\*(.+?)\*\*:?\s*(.*)", body)
        if m:
            title, detail = m.group(1).rstrip(":"), m.group(2)
        elif ": " in body[:70]:
            title, detail = body.split(": ", 1)
        else:
            title, detail = body, ""
        items.append({"title": title.strip(), "detail": detail.strip(), "cites": cites})
    return items


def _guess_source(it, events):
    """When the model did not cite, link the brief item to the event it most overlaps with."""
    words = set(re.findall(r"[a-z0-9]{4,}", (it["title"] + " " + it["detail"]).lower()))
    best = max(events, key=lambda e: len(words & set(re.findall(r"[a-z0-9]{4,}", e["text"].lower()))), default=None)
    return [best["doc_id"]] if best and "-" in best["doc_id"] and words & set(re.findall(r"[a-z0-9]{4,}", best["text"].lower())) else []


@app.get("/today", response_class=HTMLResponse)
def today_page(req: Request):
    role, user = need(req)
    b = C.latest_brief(role)
    pa, pm, cs = _counts(role)
    items = _brief_items(b["text"]) if b else []
    if b and not items:
        items = [{"title": e["text"].split(":")[0][:60], "detail": e["text"], "cites": [e["doc_id"]] if "-" in e["doc_id"] else []} for e in C._events(role)]
    cards = ""
    evs = C._events(role) if items else []
    for it in items[:5]:
        if not it["cites"]:
            it["cites"] = _guess_source(it, evs)
        ic, tone = _icon_for(it["title"] + " " + it["detail"])
        tl = (it["title"] + " " + it["detail"]).lower()
        act = ""
        if C.ROLES[role]["credit"] and pa and re.search(r"kyc|identity|id doc|renew|approval", tl):
            act = '<a class="btn ghost sm" href="/actions">Review</a>'
        elif C.ROLES[role]["credit"] and re.search(r"autopilot|overdue loans|reminder", tl):
            act = '<a class="btn sm ghost" href="/autopilot">Open autopilot</a>'
        elif pm and re.search(r"facts|memory", tl):
            act = '<a class="btn sm ghost" href="/memory">Review facts</a>'
        src = "".join(f'<a class="src" href="/doc/{c}" target="_blank">{svg("file")}View source</a>' for c in it["cites"][:1])
        more = f'<span class="sep">+{len(it["cites"]) - 1} more sources</span>' if len(it["cites"]) > 1 else ""
        cards += f"""<div class="row"><div class="ic {tone}">{svg(ic)}</div><div class="tx"><div class="tt">{_numbered(_md(C.render(it['title'], role, user, 'brief')), list(it['cites']))}</div>
            {f'<div class="dd">{_numbered(_md(C.render(it["detail"], role, user, "brief")), list(it["cites"]))}</div>' if it['detail'] else ''}<div class="meta">{src}{more}</div></div><div class="act">{act}</div></div>"""
    if not cards:
        cards = empty("spark", "Preparing your brief…", "It is generated automatically every morning at 07:30. This page updates when it's ready.")
    stats = ""
    if C.ROLES[role]["credit"]:
        if cs and (cs["h"] or cs["e"]):
            auto = f'<div class="l">Loans that need you</div><div class="v {"warn" if cs["e"] else ""}">{cs["e"]}</div><div class="d">{cs["h"]} handled by the autopilot</div>'
        else:
            auto = f'<div class="l">Overdue loans today</div><div class="v">{cs["nw"] if cs else 0}</div><div class="d">Autopilot not run yet</div>'
        stats = f"""<div class="stats" style="margin-bottom:28px"><a class="stat" href="/actions"><div class="l">Approvals waiting</div><div class="v">{pa}</div><div class="d">{'Nothing goes out until you approve' if pa else 'You are all caught up'}</div></a>
            <a class="stat" href="/autopilot">{auto}</a>
            <a class="stat" href="/memory"><div class="l">Facts to review</div><div class="v">{pm}</div><div class="d">New knowledge waiting for a person</div></a></div>"""
    elif pm:
        stats = f'<div class="stats" style="margin-bottom:28px"><a class="stat" href="/memory"><div class="l">Facts to review</div><div class="v">{pm}</div><div class="d">New knowledge waiting for a person</div></a></div>'
    when = f"Prepared at {str(b['ts'])[11:16]}" if b else "Preparing"
    refresh = f'<form method="post" action="/api/brief" class="inline"><button class="btn quiet sm" title="Generate the brief again">{svg("refresh")}Refresh</button></form>'
    body = f"""<div class="wrap">{head(f"Good morning, {html.escape(_first_name(user))}",
        f"{C.today().strftime('%A %d %B')} · Here is what changed since yesterday. ALFRED prepared it without anyone asking.",
        '<a class="btn ghost" href="/email">' + svg('mail') + 'Open as email</a>')}
    {stats}
    {panel("Your morning brief", cards, None, f'<span class="muted small">{when}</span>{refresh}').replace('class="panel"', 'class="panel brief"', 1)}</div>"""
    return P(req, "Today", body, "/today")


# ------------------------------------------------------------------ ask
SUGGEST = {
    "rm_credit": ["Which company is breaching its covenant?", "What is the SME credit limit without committee approval?", "What is our mortgage rate in Spain?"],
    "it_support": ["Why did the nightly batch fail?", "What are the branch opening hours?", "Which company is breaching its covenant?"],
    "compliance": ["When is the Bank of Italy quarterly report due?", "What does the AML alert say?", "How often must KYC be renewed?"],
}


AV = f'<div class="av">{svg("spark")}</div>'


def _answer_html(role, text, sources=None, model=None, status=None, note=""):
    if status == "denied":
        return f"""<div class="a lock">{AV}<div class="body"><div class="txt">{html.escape(text)}</div>
            <div class="ft"><span class="lock">{svg('lock')}Restricted by your role</span>{f"<span>{html.escape(note)}</span>" if note else ""}</div></div></div>"""
    order = []
    rendered = _numbered(_md(C.render(text, role)), order)
    for s in sources or []:
        if s["id"] not in order:
            order.append(s["id"])
    if status == "abstain":
        ft = '<span class="warn">No approved source covers this, so I won\'t guess</span>'
    else:
        lat = re.search(r"\(([\d.]+s)\)", model or "")
        ft = '<span class="ok">Verified against approved sources</span>' + (f"<span>Answered in {lat.group(1)}</span>" if lat else "")
    srcs = ""
    if order and status != "abstain":
        t = _titles(order)
        srcs = ('<div class="srcs">' + "".join(f'<a href="/doc/{d}" target="_blank" title="{d}"><span class="k">{i + 1}</span><span class="t">{html.escape(t.get(d) or d)}</span></a>'
                                              for i, d in enumerate(order)) + "</div>")
    nt = f'<div class="ft"><span>{html.escape(note)}</span></div>' if note else ""
    return f"""<div class="a">{AV}<div class="body"><div class="txt">{rendered}</div>{srcs}{nt}<div class="ft">{ft}</div></div></div>"""


def _question_html(t):
    return f'<div class="q"><div>{html.escape(t)}</div></div>'


@app.get("/chat", response_class=HTMLResponse)
def chat(req: Request):
    role, user = need(req)
    rows = C.q("SELECT * FROM chat_log WHERE role=? ORDER BY ts", [_chat_scope(req, role)]) if "chat_log" in [r[0] for r in C.rows("SHOW TABLES")] else []
    hist = ""
    for m in rows:
        if m["who"] == "ALFRED":
            meta = json.loads(m["meta"] or "{}")
            hist += _answer_html(role, m["text"], meta.get("sources"), meta.get("model"), meta.get("status"), meta.get("note", ""))
        else:
            hist += _question_html(m["text"])
    chips = "".join(f'<button type="button" data-q="{html.escape(s)}" onclick="ask(this.dataset.q)"><span>{html.escape(s)}</span>{svg("arrow")}</button>' for s in SUGGEST[role])
    empty_ = f"""<div class="empty" id="empty"><div class="orb">{svg('spark')}</div><h1>What do you need to know?</h1>
        <p class="sub">Answers come only from approved bank knowledge, always with sources. If it isn't there, I'll say so.</p>
        <div class="chips">{chips}</div></div>"""
    clear = (f'<div class="askbar"><form method="post" action="/chat/clear"><button class="btn ghost sm">{svg("plus")}New conversation</button></form></div>' if rows else "")
    typing = (f'<div class="a" id="typing">{AV}<div class="body"><div class="txt muted">'
              '<span class="typing"><i></i><i></i><i></i></span>&nbsp; Checking approved sources…</div></div></div>')
    body = f"""<div class="wrap narrow ask">{clear}<div class="msgs" id="msgs">{hist or empty_}</div>
      <div class="composer"><form onsubmit="event.preventDefault();ask(document.getElementById('q').value)">
      <input id="q" placeholder="Ask about policies, customers or operations…" autocomplete="off" aria-label="Your question">
      <button class="btn" aria-label="Ask" title="Ask">{svg('send', '2')}</button></form>
      <div class="hint">ALFRED only proposes. Nothing is sent or changed without your approval.</div></div></div>
    <script>
    const TYPING = {json.dumps(typing)};
    async function ask(t){{ if(!t||!t.trim())return; const m=document.getElementById('msgs'); const e=document.getElementById('empty'); if(e) e.remove();
      const q=document.getElementById('q'); q.value=''; q.disabled=true;
      m.insertAdjacentHTML('beforeend','<div class="q"><div>'+t.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</div></div>'+TYPING);
      window.scrollTo(0,document.body.scrollHeight);
      try {{ const r=await fetch('/api/ask',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{q:t}})}});
        const j=await r.json(); document.getElementById('typing').remove(); m.insertAdjacentHTML('beforeend',j.html); }}
      catch(err) {{ document.getElementById('typing').remove(); m.insertAdjacentHTML('beforeend','<div class="banner bad">Something went wrong. Please try again.</div>'); }}
      q.disabled=false; q.focus(); window.scrollTo(0,document.body.scrollHeight); }}
    window.scrollTo(0,document.body.scrollHeight);
    </script>"""
    return P(req, "Ask", body, "/chat")


@app.post("/chat/clear")
def chat_clear(req: Request):
    role, user = need(req)
    C.x("DELETE FROM chat_log WHERE role=?", [_chat_scope(req, role)])
    return RedirectResponse("/chat", 303)


@app.post("/api/ask")
async def api_ask(req: Request):
    role, user = need(req)
    qtext = (await req.json()).get("q", "")[:800]
    a = C.answer(qtext, role, actor=user)
    note = "Role claims typed in the chat are ignored. Your access comes from your sign-in." if a["meta"].get("role_claim_ignored") else ""
    scope = _chat_scope(req, role)
    C.x("INSERT INTO chat_log VALUES (now(), ?, ?, ?, ?)", [scope, user, qtext, "{}"])
    meta = {"sources": a["sources"], "model": a["model"], "status": a["status"], "note": note}
    C.x("INSERT INTO chat_log VALUES (now(), ?, 'ALFRED', ?, ?)", [scope, a["text"], json.dumps(meta, ensure_ascii=False)])
    return JSONResponse({"html": _answer_html(role, a["text"], a["sources"], a["model"], a["status"], note), "status": a["status"]})


# ------------------------------------------------------------------ morning email
@app.get("/email", response_class=HTMLResponse)
def email(req: Request):
    role, user = need(req)
    b = C.latest_brief(role)
    txt = b["text"] if b else "(not generated yet)"
    if b and not re.search(r"\[[A-Z]{2,4}-[0-9A-Za-z\-]+\]", txt):   # every brief shows where it came from, even if the model forgot to cite
        try: srcs = [d for d in json.loads(b.get("sources") or "[]") if "-" in d]
        except Exception: srcs = []
        if srcs: txt = txt.rstrip() + "\n\nSources: " + " ".join(f"[{d}]" for d in srcs[:8])
    when = str(b["ts"])[11:16] if b else "07:30"
    body = f"""<div class="wrap">{head("Morning email", f"What {_first_name(user)} finds in the inbox at 07:30. Nobody asked for it.")}
    <div class="mail"><div class="hd"><div class="ic">{svg('spark')}</div><div style="flex:1"><div class="from">ALFRED</div>
    <div class="meta">To {html.escape(user)}</div></div><div class="meta">{C.today().strftime('%a %d %b')} · {when}</div></div>
    <div class="subj">Your brief for {C.today().strftime('%A %d %B %Y')}</div>
    <div class="body">Good morning {html.escape(_first_name(user))},<br><br>{_md(C.render(txt, role, user, 'brief'))}<br><br>
    <a class="btn" href="/today">Open Today {svg('arrow')}</a></div></div></div>"""
    return P(req, "Morning email", body, "/email")


@app.post("/api/brief")
def api_brief(req: Request):
    role, user = need(req)
    C.make_brief(role, actor=f"{user} (manual run)")
    return RedirectResponse(req.headers.get("referer") or "/today", 303)


# ------------------------------------------------------------------ memory
def _fact_parts(text):
    return text.split(": ", 1) if ": " in text[:90] else ("", text)


@app.get("/memory", response_class=HTMLResponse)
def memory(req: Request):
    role, user = need(req)
    rows = C.memory_list(role)
    pend = [m for m in rows if m["status"] == "pending"]
    appr = [m for m in rows if m["status"] == "approved"]
    rej = [m for m in rows if m["status"] == "rejected"]

    def card(m):
        src_title, txt = _fact_parts(m["text"])
        return f"""<div class="row"><div class="ic warn">{svg('/memory')}</div><div class="tx"><div class="tt">{C.render(txt, role)}</div>
            <div class="meta"><span>From <a href="/doc/{m['doc_id']}" target="_blank">{html.escape(src_title or m['doc_id'])}</a></span><span class="sep idc">{html.escape(m['doc_id'])}</span></div></div>
            <div class="act"><form class="inline" method="post" action="/memory/{m['fact_id']}/rejected"><button class="btn quiet sm">{svg('x')}Reject</button></form>
            <form class="inline" method="post" action="/memory/{m['fact_id']}/approved"><button class="btn approve sm">{svg('check', '2.2')}Approve</button></form></div></div>"""

    def line(m):
        src_title, txt = _fact_parts(m["text"])
        return f"""<tr><td><div class="clamp">{C.render(txt, role)}</div></td>
            <td class="nowrap"><a href="/doc/{m['doc_id']}" target="_blank" class="small">{html.escape((src_title or m['doc_id'])[:40])}</a></td></tr>"""
    th = '<tr><th>Fact</th><th>Source</th></tr>'
    body = f"""<div class="wrap">{head("Memory", "ALFRED only answers from knowledge a person has approved. New facts wait here for review.")}
    {panel("Waiting for review", ''.join(card(m) for m in pend) or empty("check", "Nothing to review", "New facts from documents will appear here before ALFRED can use them.", tone="ok"), len(pend))}
    {section("Approved knowledge", len(appr), '<span class="hint">Used to answer questions</span>')}
    <div class="tbl"><table>{th}{''.join(line(m) for m in appr[:12])}</table></div>
    {f'<details class="more"><summary>Show all {len(appr)}</summary><div class="tbl" style="margin-top:8px"><table>{"".join(line(m) for m in appr[12:250])}</table></div></details>' if len(appr) > 12 else ''}
    {f'<details class="more" style="margin-top:20px"><summary>Rejected ({len(rej)})</summary><div class="tbl" style="margin-top:8px"><table>{"".join(line(m) for m in rej)}</table></div></details>' if rej else ''}
    {section("Teach ALFRED")}
    <div class="card"><form method="post" action="/memory/add" class="field"><input name="text" placeholder="Write a fact, e.g. “Branches close at 13:00 on Christmas Eve”" aria-label="New fact">
    <button class="btn ghost">Propose fact</button></form><div class="muted small" style="margin-top:8px">It waits for review like any other fact. Personal data is pseudonymised automatically.</div></div></div>"""
    return P(req, "Memory", body, "/memory")


@app.post("/memory/add")
def memory_add(req: Request, text: str = Form(...)):
    role, user = need(req)
    C.add_fact(C.pseudonymise_query(text.strip())[:600], "MANUAL", "credit" if C.ROLES[role]["credit"] else "it", user, role)
    return RedirectResponse("/memory", 303)


@app.post("/memory/{fid}/{decision}")
def memory_decide(req: Request, fid: str, decision: str):
    role, user = need(req)
    if decision in ("approved", "rejected") and any(m["fact_id"] == fid for m in C.memory_list(role)):   # only facts in the role's departments
        C.memory_decide(fid, decision, user, role)
    return RedirectResponse("/memory", 303)


# ------------------------------------------------------------------ approvals
def _action_text(role, a, case):
    p = json.loads(a["payload"]) if isinstance(a["payload"], str) else (a["payload"] or {})
    who = C.render(case["customer_id"], role) if case and case.get("customer_id") else C.render(str(p.get("to", "the customer")), role)
    amt = f"€{case['amount_overdue']:,.2f} overdue · {case['days_past_due']} days" if case else ""
    k = a["kind"]
    if k == "send_reminder":
        title = f"Send {'a certified-email (PEC)' if p.get('channel') == 'PEC' else 'an email'} reminder to {who}"
    elif k == "post_late_fee":
        title = f"Charge a €{p.get('amount_eur', 15)} late fee to {who}"
    elif k == "escalate":
        title = f"Hand {who} over to {html.escape(str(p.get('to', 'collections')))}"
    elif k == "draft_email":
        title = f"Email {C.render(str(p.get('to', '')), role)}: {html.escape(p.get('subject', ''))}"
    else:
        title = html.escape(k.replace("_", " "))
    why = p.get("why") or p.get("note") or (case or {}).get("reason") or ""
    why = C.render(re.sub(r"\s*\[[A-Z]{2,4}-[0-9A-Za-z\-]+\]", "", why), role) if why else ""
    det = ""
    if p.get("body"):
        det = f'<details class="pv"><summary>Preview message</summary><div class="preview">{C.render(p["body"], role)}</div></details>'
    src = "ALFRED" if a["proposed_by"] == "brain" else "Autopilot"
    return title, amt, why, det, src


@app.get("/actions", response_class=HTMLResponse)
def actions(req: Request):
    role, user = need(req)
    if not C.ROLES[role]["credit"]:
        return P(req, "Approvals", _locked("Not available for your role", "Customer actions are handled by the credit team."), "/actions")
    prop = C.q("SELECT * FROM actions WHERE status='proposed' ORDER BY CASE proposed_by WHEN 'brain' THEN 0 ELSE 1 END, action_id")
    done = C.q("SELECT * FROM actions WHERE status<>'proposed' ORDER BY ts DESC LIMIT 60")
    cases = {c["case_id"]: c for c in C.q("SELECT * FROM cases")}

    def card(a):
        title, amt, why, det, src = _action_text(role, a, cases.get(a["case_id"]))
        return f"""<div class="row"><div class="ic {'info' if src == 'Autopilot' else ''}">{svg('/autopilot' if src == 'Autopilot' else 'mail')}</div><div class="tx"><div class="tt">{title}</div>
            {f'<div class="dd clamp2">{why}</div>' if why else ''}<div class="meta"><span>Proposed by {src}</span>{f'<span class="sep num">{amt}</span>' if amt else ''}{det}</div></div>
            <div class="act"><form class="inline" method="post" action="/actions/{a['action_id']}/rejected"><button class="btn quiet sm">{svg('x')}Reject</button></form>
            <form class="inline" method="post" action="/actions/{a['action_id']}/approved"><button class="btn approve sm">{svg('check', '2.2')}Approve</button></form></div></div>"""

    def hist(a):
        title, amt, why, det, src = _action_text(role, a, cases.get(a["case_id"]))
        return f'<tr><td>{title}</td><td>{tag(a["status"])}</td><td class="muted">{html.escape(a["approved_by"] or "")}</td></tr>'
    n_auto = sum(1 for a in prop if a["proposed_by"] == "autopilot")
    bulk = (f'<form method="post" action="/autopilot/approve_all"><button class="btn">{svg("check", "2.2")}Approve all routine reminders ({n_auto})</button></form>' if n_auto and not arena_locked(req) else "")
    more = (f'<details class="more"><summary>Show {len(prop) - 20} more</summary><div class="panel" style="margin-top:8px"><div class="list">{"".join(card(a) for a in prop[20:120])}</div></div></details>'
            if len(prop) > 20 else '')
    body = f"""<div class="wrap">{head("Approvals", "Nothing is sent, charged or escalated until you approve it. Each item shows why it was proposed.", bulk)}
    {panel("Waiting for you", ''.join(card(a) for a in prop[:20]) or empty("check", "You're all caught up", "New proposals from ALFRED and the reminder autopilot will appear here.", tone="ok"), len(prop))}
    {more}
    {f'<details class="more" style="margin-top:24px"><summary>History ({len(done)})</summary><div class="tbl" style="margin-top:8px"><table><tr><th>Action</th><th>Status</th><th>Decided by</th></tr>{"".join(hist(a) for a in done)}</table></div></details>' if done else ''}</div>"""
    return P(req, "Approvals", body, "/actions")


@app.post("/actions/{aid}/{decision}")
def action_decide(req: Request, aid: str, decision: str):
    role, user = need(req)
    if C.ROLES[role]["credit"] and decision in ("approved", "rejected"):
        E.decide_action(aid, decision, user, role)
    return RedirectResponse(req.headers.get("referer") or "/actions", 303)


# ------------------------------------------------------------------ autopilot (overdue-loan reminders)
@app.get("/autopilot", response_class=HTMLResponse)
def autopilot(req: Request):
    role, user = need(req)
    if not C.ROLES[role]["credit"]:
        return P(req, "Autopilot", _locked("Not available for your role", "The reminder autopilot works on customer credit data."), "/autopilot")
    cases = C.q("""SELECT * FROM cases ORDER BY CASE status WHEN 'exception' THEN 0 WHEN 'awaiting_approval' THEN 1 ELSE 2 END, amount_overdue DESC""")
    ran = any(c["status"] != "new" for c in cases)
    k = E.kpis() if ran else None
    run = (f'<form method="post" action="/autopilot/run"><button class="btn {"ghost" if ran else ""}">'
           f'{svg("refresh" if ran else "play")}{"Run again" if ran else "Run today&#39;s reminders"}</button></form>')
    if arena_locked(req):
        run = '<span class="muted small">Public arena: the autopilot runs on the organisers&#39; schedule.</span>'
    hd = head("Reminder autopilot", "Handles routine overdue-loan reminders and stops for anything sensitive. You approve before anything goes out.", run)
    if not ran:
        body = f"""<div class="wrap">{hd}<div class="panel">{empty('/autopilot', f"{len(cases)} overdue loans in today's extract",
            "Run the reminders to sort them into routine cases, which are prepared for your approval, and sensitive cases that need a person.", run, "info")}</div>{_how(None)}</div>"""
        return P(req, "Autopilot", body, "/autopilot")
    exc = [c for c in cases if c["status"] == "exception"]
    ready = [c for c in cases if c["status"] not in ("exception", "new")]
    stats = f"""<div class="stats"><div class="stat"><div class="l">Cases today</div><div class="v">{k['cases']}</div><div class="d">From the arrears extract</div></div>
      <div class="stat"><div class="l">Handled automatically</div><div class="v">{k['straight_through']}</div><div class="d">Prepared for one-click approval</div></div>
      <a class="stat" href="#needs"><div class="l">Need your review</div><div class="v warn">{len(exc)}</div><div class="d">Sensitive or unusual</div></a>
      <div class="stat"><div class="l">Time saved today</div><div class="v ok">≈ {k['minutes_saved'] / 60:.1f}<small>h</small></div><div class="d">vs. checking every case by hand</div></div></div>"""

    def need_card(c):
        why = E.EXC_LABEL.get(c["exception"], (c["exception"] or "").replace("_", " "))
        return f"""<div class="row"><div class="ic warn">{svg('alert')}</div><div class="tx"><div class="tt">{C.render(c['customer_id'] or '', role)} <span class="muted" style="font-weight:400">·</span> {html.escape(why)}</div>
            <div class="dd clamp2">{html.escape(c['reason'] or '')}</div>
            <div class="meta"><span class="num">€{c['amount_overdue']:,.2f} overdue</span><span class="sep">{c['days_past_due']} days late</span><a class="sep" href="/audit?case={c['case_id']}">View trail</a></div></div>
            <div class="act"><form class="inline" method="post" action="/autopilot/case/{c['case_id']}/hold"><button class="btn quiet sm">{svg('pause')}Hold</button></form>
            <form class="inline" method="post" action="/autopilot/case/{c['case_id']}/proceed"><button class="btn ghost sm">{svg('send')}Send reminder anyway</button></form></div></div>"""
    rows = "".join(f"""<tr><td>{C.render(c['customer_id'] or '', role)}<span class="two"><a class="muted" href="/audit?case={c['case_id']}">View trail</a></span></td><td class="amt">€{c['amount_overdue']:,.2f}</td><td class="num">{c['days_past_due']} days</td>
        <td>{html.escape(E.LABEL.get(c['decision'], c['decision'] or ''))}</td><td>{tag(c['status'], 'waiting for you' if c['status'] == 'awaiting_approval' else None)}</td></tr>""" for c in ready)
    hours_manual, hours_auto = k["manual_minutes"] / 60, k["autopilot_minutes"] / 60
    eur_h = 35
    biz = f"""<div class="card" style="margin-top:12px"><div class="ch"><span style="color:var(--ok);display:flex">{svg('up')}</span><h2>Why it matters</h2></div>
      <div style="color:var(--ink2);line-height:1.65">Today a credit officer checks every overdue loan by hand: {k['cases']} cases × 12 min = <b>{hours_manual:.1f} h</b>
      (≈ €{hours_manual * eur_h:,.0f} of staff time), and customers with <b>€{k['overdue_eur']:,.0f}</b> overdue wait longer to be contacted.
      With the autopilot the same work takes <b>{hours_auto:.1f} h</b>: <b style="color:var(--ok)">{hours_manual - hours_auto:.1f} h saved today</b>
      (≈ €{(hours_manual - hours_auto) * eur_h:,.0f}/day, ≈ €{(hours_manual - hours_auto) * eur_h * 220 / 1000:,.0f}k/year over 220 working days),
      and every sensitive case still gets a human.</div>
      <div class="muted small" style="margin-top:10px">Assumptions: 12 min to check a case by hand, 1 min to approve a prepared one, €35/h loaded staff cost, 220 working days. Exceptions keep their full 12 min.
      · <a href="/outbox">Outbox &amp; exports →</a></div></div>"""
    needs = panel("Needs you", "".join(need_card(c) for c in exc[:12]) or empty("check", "No sensitive cases today", tone="ok"), len(exc),
                  '<span class="muted small">Stopped by policy, waiting for a person</span>')
    body = f"""<div class="wrap">{hd}{stats}{biz}
    <div id="needs" style="margin-top:32px">{needs}</div>
    {f'<details class="more"><summary>Show {len(exc) - 12} more</summary><div class="panel" style="margin-top:8px"><div class="list">{"".join(need_card(c) for c in exc[12:])}</div></div></details>' if len(exc) > 12 else ''}
    {section("Ready to send", len(ready), '<a class="btn sm" href="/actions">Review in Approvals ' + svg('arrow') + '</a>')}
    <div class="tbl"><table><tr><th>Customer</th><th class="r">Overdue</th><th>Late by</th><th>Next step</th><th>Status</th></tr>{rows}</table></div>{_how(k)}</div>"""
    return P(req, "Autopilot", body, "/autopilot")


def _how(k):
    acc = ""
    if k and k.get("gold_n"):
        acc = (f"<li>Checked against the bank's labelled cases: rules {k['rule_accuracy']}% · AI triage agreement "
               f"{k['model_accuracy'] if k['model_accuracy'] is not None else '–'}% · sensitive cases caught {k['exceptions_caught']}.</li>")
    saved = f"<li>Time saved assumes 12 minutes to check a case by hand and 1 minute to approve a prepared one (manual {k['manual_minutes'] // 60} h → {k['autopilot_minutes'] // 60} h).</li>" if k else ""
    return f"""<details style="margin-top:32px"><summary>How it works</summary><div class="card" style="margin-top:10px"><ul style="margin:0;padding-left:18px;color:var(--ink2);line-height:1.8">
      <li>Input: today's arrears extract from core banking, pseudonymised before the AI sees it.</li>
      <li>Policy (POL-0003): 1-30 days polite email; 31-60 days formal certified email + €15 fee; 61-90 days final notice and collections; over 90 days legal.</li>
      <li>It always stops for: deceased or vulnerable customers, forbearance, open complaints or disputes, recent partial payments, amounts over €5,000, or when the AI disagrees with the rules.</li>
      <li>Every decision and approval is written to the <a href="/audit?event=case_evaluated">audit trail</a>.</li>{acc}{saved}</ul></div></details>"""


def _arena_blocked(req, role, user, what):
    C.audit(user, role, "arena_public_blocked", None, {"what": what})
    return JSONResponse({"error": "arena_public_blocked", "message": f"On the public arena, {what} is not available to teams."}, 403)


@app.post("/autopilot/run")
def autopilot_run(req: Request):
    role, user = need(req)
    if arena_locked(req):
        return _arena_blocked(req, role, user, "an on-demand autopilot run")
    if C.ROLES[role]["credit"]:
        E.run(user, role)
    return RedirectResponse("/autopilot", 303)


@app.post("/autopilot/approve_all")
def autopilot_approve_all(req: Request):
    role, user = need(req)
    if arena_locked(req):
        return _arena_blocked(req, role, user, "bulk approval")
    if C.ROLES[role]["credit"]:
        E.approve_all_straight(user, role)
    return RedirectResponse(req.headers.get("referer") or "/actions", 303)


@app.post("/autopilot/case/{cid}/{decision}")
def autopilot_case(req: Request, cid: str, decision: str):
    role, user = need(req)
    if C.ROLES[role]["credit"] and decision in ("hold", "proceed"):
        E.resolve_exception(cid, decision, user, role)
    return RedirectResponse("/autopilot", 303)


@app.get("/outbox", response_class=HTMLResponse)
def outbox_page(req: Request):
    role, user = need(req)
    from autopilot import outbox
    if not C.ROLES[role]["credit"]:
        return P(req, "Outbox", _locked("Not available for your role", "The outbox holds customer letters for the credit team."), "/outbox")
    fs = outbox.files()
    rows = "".join(f'<tr><td><a href="/outbox/file/{html.escape(f["name"])}" style="display:inline-flex;gap:8px;align-items:center">{svg("file")}{html.escape(f["name"])}</a></td>'
                   f'<td class="amt muted" style="font-weight:400">{f["bytes"]:,} bytes</td><td class="muted num">{f["mtime"]:%d/%m %H:%M:%S}</td></tr>' for f in fs)
    body = f"""<div class="wrap">{head("Outbox &amp; exports", "The finished output of the autopilot: reminder letters and the batch file for the PEC gateway and core banking. "
        "Files appear here only after a person approves. Real names are filled in at this point, for approved items only.")}
    {f'<div class="tbl"><table><tr><th>File</th><th class="r">Size</th><th>Written</th></tr>{rows}</table></div>' if fs else
     '<div class="panel">' + empty("/outbox", "Nothing has left the bank", "Files appear here after you approve reminders in Approvals.", '<a class="btn ghost" href="/actions">Go to Approvals</a>') + '</div>'}</div>"""
    return P(req, "Outbox", body, "/outbox")


@app.get("/outbox/file/{name:path}")
def outbox_file(req: Request, name: str):
    role, user = need(req)
    from autopilot import outbox
    from fastapi.responses import PlainTextResponse
    p = os.path.realpath(os.path.join(outbox.OUT, name))
    if not C.ROLES[role]["credit"] or not p.startswith(os.path.realpath(outbox.OUT)) or not os.path.isfile(p):
        return PlainTextResponse("not found", 404)
    C.audit(user, role, "outbox_file_viewed", name, {})
    txt = open(p).read()
    return PlainTextResponse(C.pseudonymise_query(txt) if team_of(req) else txt)   # arena teams: letters stay pseudonymised


# ------------------------------------------------------------------ audit + sources
@app.get("/audit", response_class=HTMLResponse)
def audit(req: Request, event: str = "", case: str = ""):
    role, user = need(req)
    if case:   # the full story of one case, oldest first: input + rule + model, proposal, approver, execution, outbox file
        rows = C.q("SELECT * FROM audit WHERE object_id = ? OR object_id LIKE ? ORDER BY ts", [case, f"A-{case}-%"])
    else:
        rows = C.q("SELECT * FROM audit WHERE (? = '' OR event = ?) ORDER BY ts DESC LIMIT 300", [event, event])
    evs = [r["event"] for r in C.q("SELECT DISTINCT event FROM audit ORDER BY 1")]
    filt = "".join(f'<a class="{"on" if e == event else ""}" href="/audit?event={e}">{e.replace("_", " ").capitalize()}</a>' for e in evs)
    tone = {"security_injection_attempt": "rejected", "access_denied": "rejected", "injection_flagged": "rejected", "action_approved": "approved",
            "action_executed": "executed", "action_rejected": "rejected", "fact_approved": "approved", "abstain": "pending", "re_identification": "pending"}
    def row(r):
        d = r["detail"] or "{}"
        try: d = json.dumps(json.loads(d), ensure_ascii=False, indent=1)
        except Exception: pass
        ts = str(r['ts'])
        return f"""<tr><td class="nowrap num">{ts[:10]}<span class="two">{ts[11:19]}</span></td><td>{html.escape(r['actor'] or '')}<span class="two">{html.escape(C.ROLES.get(r['role'], {}).get('label', r['role'] or ''))}</span></td>
               <td>{tag(tone.get(r['event'], 'plain'), (r['event'] or '').replace('_', ' ').capitalize())}</td><td class="idc">{html.escape(r['object_id'] or '–')}</td>
               <td><details><summary>Details</summary><div class="mono">{C.render(d[:3000], role)}</div></details></td></tr>"""
    title = f"Trail for {html.escape(case)}" if case else "Audit trail"
    body = f"""<div class="wrap wide">{head(title, "Who did what, when, and on which input. Every proposal, approval, re-identification and blocked attempt is written here.")}
    {'' if case else f'<div class="filters"><a class="{"on" if not event else ""}" href="/audit">All events</a>{filt}</div>'}
    <div class="tbl"><table><tr><th style="width:120px">When</th><th>Who</th><th>What</th><th>Item</th><th style="width:34%"></th></tr>{''.join(row(r) for r in rows)}</table>
    {'' if rows else empty('/audit', 'No events yet')}</div></div>"""
    return P(req, "Audit trail", body, "/audit")


# ------------------------------------------------------------------ security (live view of blocked attempts, read from the audit table)
REDTEAM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "redteam", "report.json")
SEC_EVENTS = ("security_injection_attempt", "access_denied", "injection_flagged")
SEC_LABEL = {"security_injection_attempt": ("Prompt injection", "Tried to override the assistant's rules; refused and logged."),
             "access_denied": ("Access denied", "Asked for data outside the role's access; nothing was retrieved."),
             "injection_flagged": ("Poisoned document", "A document contained instructions to the AI; treated as data only."),
             "role_claim": ("Role claim ignored", "Claimed a different role in the chat; access comes from the sign-in only.")}


def _pseudo_only(t):
    """Escape and show pseudonyms as masked chips. Never re-identifies, whatever the viewer's role."""
    return re.sub(r"&lt;([A-Z][A-Z_]*_\d+)&gt;", r'<span class="pseudo">&lt;\1&gt;</span>', html.escape(t or ""))


def _pct(v):
    return f"{v * 100:.0f}%" if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 else html.escape(str(v))


def _scoreboard():
    try:
        rep = json.load(open(REDTEAM))
    except Exception:
        return panel("Red-team scoreboard", empty("shield", "No red-team run yet",
                     "The scoreboard appears here automatically when the red-team arena writes its report."))
    if not isinstance(rep, dict):
        return panel("Red-team scoreboard", empty("shield", "Report format not recognised"))
    scal = [(k, v) for k, v in rep.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool) and len(str(v)) < 40
            and k not in ("generated_at", "ts", "timestamp", "date", "run_id", "model", "version")][:4]
    def tone(k, v):
        bad = any(w in k.lower() for w in ("leak", "unauthor", "success", "asr", "breach"))
        return ("ok" if not v else "warn") if bad and isinstance(v, (int, float)) else ""
    stats = ('<div class="stats" style="border:0;border-radius:0;box-shadow:none;border-bottom:1px solid var(--line)">' + "".join(
        f'<div class="stat"><div class="l">{html.escape(k.replace("_", " ").capitalize())}</div><div class="v {tone(k, v)}">{_pct(v) if "rate" in k.lower() or "asr" in k.lower() else html.escape(str(v))}</div></div>'
        for k, v in scal) + "</div>") if scal else ""
    cats = next((rep[k] for k in ("categories", "by_category", "per_category", "category") if k in rep), None)
    if isinstance(cats, dict):
        cats = [{"category": k, **(v if isinstance(v, dict) else {"value": v})} for k, v in cats.items()]
    table = ""
    if isinstance(cats, list) and cats and isinstance(cats[0], dict):
        cols = [c for c in cats[0].keys() if c not in ("category", "name")][:5]
        def cell(c, v):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and ("rate" in c.lower() or "asr" in c.lower()):
                w = max(0, min(100, v * 100 if v <= 1 else v))
                col = "var(--ok)" if w == 0 else "var(--warn)" if w < 10 else "var(--bad)"
                return (f'<td class="num"><span style="display:inline-flex;align-items:center;gap:10px"><span style="width:80px;height:6px;border-radius:3px;background:var(--surface2);overflow:hidden">'
                        f'<span style="display:block;height:100%;width:{max(w, 2):.0f}%;background:{col}"></span></span>{_pct(v) if v <= 1 else f"{v:.0f}%"}</span></td>')
            return f'<td class="num">{html.escape(str(v))}</td>'
        table = (f'<table><tr><th>Category</th>{"".join(f"<th>{html.escape(c.replace(chr(95), chr(32)).capitalize())}</th>" for c in cols)}</tr>'
                 + "".join(f'<tr><td>{html.escape(str(r.get("category") or r.get("name") or "").replace("_", " ").capitalize())}</td>{"".join(cell(c, r.get(c, "")) for c in cols)}</tr>' for r in cats[:20]) + "</table>")
    when = html.escape(str(rep.get("generated_at") or rep.get("ts") or ""))[:19]
    return (f'<div class="panel"><div class="ph2"><h2>Red-team scoreboard</h2><div class="r muted small">{("Last run " + when) if when else "From runs/redteam/report.json"}</div></div>'
            f'{stats}{table or (empty("shield", "No per-category results in the report") if not stats else "")}</div>')


@app.get("/security", response_class=HTMLResponse)
def security(req: Request):
    role, user = need(req)
    if not C.ROLES[role]["credit"]:
        return P(req, "Security", _locked("Not available for your role", "The security view is for the credit and compliance teams."), "/security")
    ph = ",".join("?" * len(SEC_EVENTS))
    cond = f"(event IN ({ph}) OR detail LIKE '%\"role_claim_ignored\": true%')"
    rows = C.q(f"SELECT * FROM audit WHERE {cond} ORDER BY ts DESC LIMIT 20", list(SEC_EVENTS))
    today = C.q(f"""SELECT count(*) n, count(*) FILTER (WHERE event='security_injection_attempt') inj, count(*) FILTER (WHERE event='access_denied') den,
                   count(*) FILTER (WHERE detail LIKE '%\"role_claim_ignored\": true%') claim, count(*) FILTER (WHERE event='injection_flagged') doc
                   FROM audit WHERE {cond} AND ts >= current_date""", list(SEC_EVENTS))[0]
    stats = f"""<div class="stats"><div class="stat"><div class="l">Attacks blocked today</div><div class="v">{today['n']}</div><div class="d">Every one is in the audit trail</div></div>
      <a class="stat" href="/audit?event=security_injection_attempt"><div class="l">Prompt injections</div><div class="v">{today['inj']}</div><div class="d">Refused and logged</div></a>
      <a class="stat" href="/audit?event=access_denied"><div class="l">Access denied</div><div class="v">{today['den']}</div><div class="d">Outside the asker's role</div></a>
      <div class="stat"><div class="l">Role claims ignored</div><div class="v">{today['claim']}</div><div class="d">Access comes from sign-in</div></div></div>"""

    def row(r):
        try: d = json.loads(r["detail"] or "{}")
        except Exception: d = {}
        kind = r["event"] if r["event"] in SEC_EVENTS else "role_claim"
        name, reason = SEC_LABEL[kind]
        txt = d.get("question_pseudonymised") or (C.pseudonymise_query(d["q"]) if d.get("q") else "") or (f"Document {r['object_id']}" if r["object_id"] else "")
        ts = str(r["ts"])
        return f"""<tr><td class="nowrap num">{ts[11:19]}<span class="two">{ts[:10]}</span></td>
            <td>{html.escape(r['actor'] or '')}<span class="two">{html.escape(C.ROLES.get(r['role'], {}).get('label', r['role'] or ''))}</span></td>
            <td>{tag('rejected', name)}</td><td><div class="clamp" style="color:var(--ink)">{_pseudo_only(txt[:240]) or '<span class="muted">–</span>'}</div><span class="two">{reason}</span></td></tr>"""
    recent = (f'<div class="tbl"><table><tr><th style="width:110px">When</th><th style="width:200px">Who</th><th style="width:170px">Type</th><th>Attempt (pseudonymised)</th></tr>{"".join(row(r) for r in rows)}</table></div>'
              if rows else f'<div class="panel">{empty("shieldok", "No blocked attempts yet", "Prompt injections, out-of-role requests and role claims will appear here the moment they happen.", tone="ok")}</div>')
    body = f"""<div class="wrap">{head("Security", "Live view of what ALFRED blocked, read straight from the audit trail. Text is always shown pseudonymised.",
        '<a class="btn ghost" href="/audit">' + svg('/audit') + 'Full audit trail</a>')}
    {stats}
    {section("Recent blocked attempts", len(rows), '<span class="hint">Last 20</span>')}{recent}
    <div style="margin-top:32px">{_scoreboard()}</div></div>"""
    return P(req, "Security", body, "/security")


@app.get("/docs", response_class=HTMLResponse)
def docs(req: Request):
    role, user = need(req)
    depts = C.ROLES[role]["depts"]
    ph = ",".join("?" * len(depts))
    rows = C.q(f"SELECT doc_id, kind, department, title, created_at, anon_text FROM documents WHERE department IN ({ph}) ORDER BY created_at DESC, doc_id", depts)
    tr = "".join(f"""<tr><td><a href="/doc/{r['doc_id']}">{html.escape(r['title'] or r['doc_id'])}</a>
                 {' <span class="tag rejected" style="margin-left:6px">Blocked: instructions to the AI</span>' if C.injection(r['anon_text']) else ''}</td>
                 <td>{tag('plain', r['kind'].replace('_', ' ').capitalize())}</td><td class="idc">{r['doc_id']}</td><td class="muted nowrap num">{str(r['created_at'])[:10]}</td></tr>""" for r in rows)
    body = f"""<div class="wrap">{head("Sources", f"{len(rows)} documents your role can see, with personal data pseudonymised.")}
    <div class="tbl"><table><tr><th>Document</th><th>Type</th><th>ID</th><th>Date</th></tr>{tr}</table></div></div>"""
    return P(req, "Sources", body, "/docs")


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def doc(req: Request, doc_id: str):
    role, user = need(req)
    d = C.q("SELECT * FROM documents WHERE doc_id=?", [doc_id])
    if not d:
        m = {"AUTOPILOT": "/autopilot", "APPROVALS": "/actions", "MEMORY": "/memory"}.get(doc_id)
        if m: return RedirectResponse(m, 303)
        return P(req, "Not found", _locked("Document not found", "It may have been removed, or the link is wrong."))
    d = d[0]
    if d["department"] not in C.ROLES[role]["depts"]:
        C.audit(user, role, "access_denied", doc_id, {"department": d["department"]})
        return P(req, "Source", _locked("This document is outside your access", f'It belongs to the {html.escape(d["department"])} team. This attempt was logged.'), "/docs")
    inj = (f'<div class="banner bad">{svg("alert")}<div><b>Blocked: this message contains instructions aimed at the AI.</b> ALFRED treats document text as data, '
           'so nothing was extracted, sent or approved.</div></div>') if C.injection(d["anon_text"]) else ""
    reid = ("Names with a dotted underline are shown because your role allows it; this view is logged." if C.ROLES[role]['reid']
            else "Personal data is pseudonymised for your role.")
    sugg = '' if C.injection(d['anon_text']) else f'<form method="post" action="/memory/extract/{doc_id}"><button class="btn ghost sm">{svg("spark")}Suggest facts from this document</button></form>'
    body = f"""<div class="wrap narrow" style="margin:0 auto"><div style="margin-bottom:12px"><a class="link" href="/docs">← All sources</a></div>
    {head(html.escape(d['title'] or doc_id), f"{d['kind'].replace('_', ' ').capitalize()} · {str(d['created_at'])[:10]} · <span class='idc'>{doc_id}</span>", sugg)}
    {inj}<div class="reader">{C.render(d['anon_text'], role, user, doc_id)}</div>
    <p class="muted small" style="display:flex;gap:6px;align-items:center;margin-top:12px">{svg('lock')}{reid}</p></div>"""
    return P(req, "Source", body, "/docs")


@app.post("/memory/extract/{doc_id}")
def memory_extract(req: Request, doc_id: str):
    role, user = need(req)
    C.extract_new_facts(doc_id, user, role)
    return RedirectResponse("/memory", 303)


@app.post("/admin/reset")
def admin_reset(req: Request):
    tok = os.environ.get("ADMIN_TOKEN")
    if tok and req.headers.get("x-admin-token") != tok:   # only the operator's machine can reset the demo
        C.audit("anonymous", "-", "security_admin_reset_blocked", None, {"ip": req.client.host if req.client else None})
        return JSONResponse({"error": "forbidden"}, status_code=403)
    C.reset()
    from autopilot import outbox
    outbox.clear()
    for r in C.ROLES:   # a fresh day: the 07:30 scheduler job runs again, so the brain has already spoken when anyone logs in
        try: C.make_brief(r)
        except Exception as e: C.audit("scheduler", r, "brief_failed", None, {"error": str(e)[:200]})
    return RedirectResponse("/login", 303)


def _trail(case_id):
    return [{"ts": str(r["ts"]), "actor": r["actor"], "role": r["role"], "event": r["event"], "object": r["object_id"], "detail": json.loads(r["detail"] or "{}")}
            for r in C.q("SELECT * FROM audit WHERE object_id = ? OR object_id LIKE ? ORDER BY ts", [case_id, f"A-{case_id}-%"])]


@app.get("/api/trail/{case_id}")
def api_trail(req: Request, case_id: str):
    role, user = need(req)
    if not C.ROLES[role]["credit"]:
        return JSONResponse({"error": "not available for your role"}, 403)
    return JSONResponse(_trail(case_id))


@app.get("/api/state")
def api_state(req: Request):
    """Read-only snapshot for auditors/jury (credit roles): case statuses, action statuses, outbox files."""
    role, user = need(req)
    if not C.ROLES[role]["credit"]:
        return JSONResponse({"error": "not available for your role"}, 403)
    from autopilot import outbox
    return JSONResponse({"cases": C.q("SELECT case_id, status, decision, exception FROM cases ORDER BY case_id"),
                         "actions": C.q("SELECT action_id, kind, case_id, status, proposed_by, approved_by FROM actions ORDER BY action_id"),
                         "memory": C.q("SELECT fact_id, status, text FROM memory ORDER BY fact_id"),
                         "outbox": [f["name"] for f in outbox.files()]})


# ------------------------------------------------------------------ public REST API (/v1) + metrics dashboard
from app import api as _api, dashboard as _dash
_api.install(app)
if os.environ.get("ARENA_MODE", "1") != "0":   # public "Attack ALFRED" arena (/arena, /v1/arena/*); on by default
    from app import arena as _arena
    _arena.USERS = USERS
    if not _arena.install(app):
        _arena = None


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    """Public, no login, no personal data: aggregated test, red-team and model metrics. Refreshes every 30 s."""
    return HTMLResponse(_dash.render(_api.metrics_summary()))


@app.get("/health")
def health():
    return {"db": C.SOURCE_USED, "llm": llm.status(), "docs": C.q("SELECT count(*) n FROM documents")[0]["n"]}
