"""Company Brain core: DB, vault (de)pseudonymisation, role-filtered retrieval over APPROVED memory, Q&A with citations,
abstention, proactive briefs, memory curation. English UI/answers."""
import contextvars, json, os, re, shutil, threading, datetime as dt, html
import duckdb

from . import llm
try:  # shared prompt builders (same ones the student was distilled on)
    from llm import prompts as _P  # type: ignore
    assert hasattr(_P, "messages")
    PM = _P.messages
except Exception:
    from . import prompts_local as _P
    PM = _P.messages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DB = os.environ.get("BANK_DB") or os.path.join(ROOT, "data", "bank.duckdb")
DEV_DB = os.path.join(ROOT, "runs", "dev_bank.duckdb")
APP_DB = os.environ.get("APP_DB") or os.path.join(ROOT, "runs", "app_bank.duckdb")
ABSTAIN = "I DON'T KNOW"

ROLES = {
    "rm_credit": {"label": "Relationship Manager · Credit", "short": "Finance", "depts": ["credit", "compliance", "all"], "reid": True, "credit": True},
    "it_support": {"label": "IT Support Engineer", "short": "Tech", "depts": ["it", "all"], "reid": False, "credit": False},
    "compliance": {"label": "Compliance Officer", "short": "Compliance", "depts": ["compliance", "credit", "aml", "all"], "reid": True, "credit": True},
}
PSEUDO_RE = re.compile(r"<([A-Z][A-Z_]*_\d+)>")
INJECTION_RE = re.compile(r"(ignor\w*\s+(all\s+|the\s+|tutte\s+)?(le\s+)?(previous|prior|above|istruzioni)\s*(instructions|precedenti)?"
                          r"|disregard\s+(all|previous|prior)|system\s*prompt|jailbreak|(full|complete)\s+customer\s+list|elenco\s+(completo\s+)?(dei\s+)?clienti)", re.I)
CREDIT_RE = re.compile(r"(mortgage|loan|credit|exposure|instal|arrear|overdue|reminder|covenant|iban|tax code|vat|client|customer|kyc|aml|"
                       r"money laundering|debt|ebitda|NDG|mutu|prestit|fido|cliente)", re.I)
ABSTAIN_SCORE = float(os.environ.get("ABSTAIN_SCORE", "1.0"))
STOP = set("the a an of to is are was were be what who whom how which why when where for in on at by and or does do did our we us you your "
           "i me my it its this that these those there with from as can could should would will any all about tell please give show "
           "il lo la di e che".split())

_lock = threading.RLock()
_con = None
SOURCE_USED = None


# ---------------------------------------------------------------- DB
def _prepare_db(reset=False):
    os.makedirs(os.path.dirname(APP_DB), exist_ok=True)
    src = SRC_DB if os.path.exists(SRC_DB) else DEV_DB
    if src == DEV_DB and not os.path.exists(DEV_DB):
        from app import devseed
        devseed.build(DEV_DB)
    if reset or not os.path.exists(APP_DB) or os.path.getmtime(src) > os.path.getmtime(APP_DB):
        for p in (APP_DB, APP_DB + ".wal"):
            if os.path.exists(p): os.remove(p)
        shutil.copyfile(src, APP_DB)
        return src, True
    return src, False


def con():
    global _con, SOURCE_USED
    if _con is None:
        src, fresh = _prepare_db()
        SOURCE_USED = src
        _con = duckdb.connect(APP_DB)
        _con.execute("INSTALL fts; LOAD fts;")
        _ensure(_con, fresh)
    return _con


def reset():
    global _con, _vault_cache
    with _lock:
        if _con is not None:
            _con.close(); _con = None
        _vault_cache = None
        _prepare_db(reset=True)
        con()


def q(sql, params=None):
    with _lock:
        cur = con().execute(sql, params or [])
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def rows(sql, params=None):
    """Raw tuples, under the same lock (the shared DuckDB connection refuses concurrent calls)."""
    with _lock:
        return con().execute(sql, params or []).fetchall()


def x(sql, params=None):
    with _lock:
        con().execute(sql, params or [])


def _cols(c, table):
    return [r[0] for r in c.execute(f"DESCRIBE {table}").fetchall()]


def _ensure(c, fresh):
    c.execute("CREATE TABLE IF NOT EXISTS memory(fact_id VARCHAR, doc_id VARCHAR, department VARCHAR, text VARCHAR, status VARCHAR, decided_by VARCHAR, decided_at TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS actions(action_id VARCHAR, kind VARCHAR, case_id VARCHAR, payload JSON, status VARCHAR, proposed_by VARCHAR, approved_by VARCHAR, ts TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS audit(ts TIMESTAMP, actor VARCHAR, role VARCHAR, event VARCHAR, object_id VARCHAR, detail JSON)")
    c.execute("CREATE TABLE IF NOT EXISTS chat_log(ts TIMESTAMP, role VARCHAR, who VARCHAR, text VARCHAR, meta JSON)")
    c.execute("CREATE TABLE IF NOT EXISTS briefs(role VARCHAR, ts TIMESTAMP, text VARCHAR, model VARCHAR, sources JSON)")
    c.execute("CREATE TABLE IF NOT EXISTS triage_log(case_id VARCHAR, rule_decision VARCHAR, rule_exception VARCHAR, llm_decision VARCHAR, "
              "llm_exception VARCHAR, model VARCHAR, ts TIMESTAMP)")
    tables = [r[0] for r in c.execute("SHOW TABLES").fetchall()]
    if "cases" in tables and "recent_payment" not in _cols(c, "cases"):
        c.execute("ALTER TABLE cases ADD COLUMN recent_payment BOOLEAN")
    if "cases" in tables:
        c.execute("CREATE TABLE IF NOT EXISTS cases_input AS SELECT * FROM cases")  # the raw arrears extract, kept untouched
    c.execute("PRAGMA create_fts_index('documents', 'doc_id', 'title', 'anon_text', stemmer='english', stopwords='english', strip_accents=1, overwrite=1)")
    if not c.execute("SELECT count(*) FROM memory").fetchone()[0]:
        _seed_memory(c)
    _reindex_memory(c)


def _seed_memory(c):
    """Shared memory at demo start: facts the team curated last week are approved; today's new candidates are pending.
    The SME-limit pair (policy v3 vs. the planted wrong chat claim) is left pending so the jury can approve one and reject the other."""
    planted = dict(c.execute("SELECT name, doc_id FROM planted_events").fetchall()) if "planted_events" in [r[0] for r in c.execute("SHOW TABLES").fetchall()] else {}
    docs = c.execute("SELECT doc_id, kind, department, title, anon_text, created_at FROM documents ORDER BY doc_id").fetchall()
    n = 0
    pend_ids = {planted.get("wrong_fact")}
    for doc_id, kind, dep, title, text, created in docs:
        if INJECTION_RE.search(text or ""):
            continue
        t = (text or "").strip()
        if kind == "policy":
            # one fact per sentence for policies (precise retrieval); the newest credit policy goes to the pending queue
            sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip()) > 25]
            is_new_policy = bool(re.search(r"v3|supersedes|replaces", t, re.I)) and dep == "credit"
            superseded = bool(re.search(r"\bv2\b", title or "", re.I)) and dep == "credit"
            for s in sents:
                n += 1
                status = "pending" if is_new_policy and re.search(r"limit|SME|PMI|credit line", s, re.I) else ("rejected" if superseded else "approved")
                c.execute("INSERT INTO memory VALUES (?,?,?,?,?,?,?)", [f"F-{n:04d}", doc_id, dep, f"{title}: {s}", status,
                          None if status == "pending" else "curation team (seed)", None if status == "pending" else dt.datetime(2026, 11, 14, 9, 0)])
            continue
        n += 1
        status = "pending" if doc_id in pend_ids else "approved"
        c.execute("INSERT INTO memory VALUES (?,?,?,?,?,?,?)", [f"F-{n:04d}", doc_id, dep, f"{title}: {t[:700]}", status,
                  None if status == "pending" else "curation team (seed)", None if status == "pending" else dt.datetime(2026, 11, 14, 9, 0)])


def _reindex_memory(c=None):
    c = c or con()
    if c.execute("SELECT count(*) FROM memory").fetchone()[0]:
        c.execute("PRAGMA create_fts_index('memory', 'fact_id', 'text', stemmer='english', stopwords='english', strip_accents=1, overwrite=1)")


def today():
    try:
        d = q("SELECT max(created_at)::DATE AS d FROM documents")[0]["d"]
        return d or dt.date.today()
    except Exception:
        return dt.date.today()


def audit(actor, role, event, object_id=None, detail=None):
    x("INSERT INTO audit VALUES (now(), ?, ?, ?, ?, ?)", [actor, role, event, object_id, json.dumps(detail or {}, ensure_ascii=False, default=str)])


# ---------------------------------------------------------------- vault
_vault_cache = None


def vault():
    global _vault_cache
    if _vault_cache is None:
        _vault_cache = {r["pseudonym"].strip("<>"): (r["label"], r["real_value"]) for r in q("SELECT pseudonym, label, real_value FROM vault")}
    return _vault_cache


def pseudonymise_query(text):
    """Real identifiers typed by the user -> their pseudonyms (the index only holds pseudonymised text). Uses the vault, longest match first."""
    pairs = sorted(((v[1], k) for k, v in vault().items() if v[1] and len(v[1]) >= 5), key=lambda p: -len(p[0]))
    out, low = text, text.lower()
    for real, ps in pairs:
        if real.lower() in low:
            out = re.sub(re.escape(real), f"<{ps}>", out, flags=re.I); low = out.lower()
    return out


NO_REID = contextvars.ContextVar("no_reid", default=False)   # set per request for arena team sessions: pseudonyms stay masked


def render(text, role, audit_actor=None, object_id=None):
    """HTML-escape, then show pseudonyms re-identified (authorised roles only) or as masked chips. [DOC-ID] citations become links."""
    t = html.escape(text or "")
    allowed = ROLES.get(role, {}).get("reid", False) and not NO_REID.get()
    revealed = []

    def sub(m):
        key = m.group(1); v = vault().get(key)
        if allowed and v:
            revealed.append(key)
            return f'<span class="reid" title="&lt;{key}&gt; re-identified for your role">{html.escape(v[1])}</span>'
        return f'<span class="pseudo" title="pseudonymised">&lt;{key}&gt;</span>'

    t = re.sub(r"&lt;([A-Z][A-Z_]*_\d+)&gt;", sub, t)
    t = re.sub(r"\[([A-Z]{2,4}-[0-9A-Za-z\-]+)\]", r'<a class="cite" href="/doc/\1" target="_blank">\1</a>', t)
    t = t.replace("\n", "<br>")
    if revealed and audit_actor:
        audit(audit_actor, role, "re_identification", object_id, {"pseudonyms": sorted(set(revealed))[:20]})
    return t


import base64 as _b64, unicodedata as _ud
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})


def normalise(text):
    """Undo common obfuscation before any security check: unicode tricks, zero-width chars, s p a c e d letters, l33t, base64 payloads."""
    t = _ud.normalize("NFKC", text or "")
    t = re.sub(r"[\u200b-\u200f\u2060\ufeff\u00ad]", "", t)
    t = re.sub(r"\b(?:\w[ .\-_*]){3,}\w\b", lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), t)   # i g n o r e -> ignore
    out = [t, t.translate(_LEET)]
    for tok in re.findall(r"[A-Za-z0-9+/=]{16,}", t):
        try:
            d = _b64.b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8")
            if d.isprintable(): out.append(d)
        except Exception:
            pass
    return " || ".join(out)


def injection(text):
    return bool(INJECTION_RE.search(normalise(text)))


# ---------------------------------------------------------------- retrieval
def _query_terms(qtext):
    toks = re.findall(r"<[A-Z_]+_\d+>|[\wÀ-ÿ']+", qtext.lower())
    return " ".join(t.strip("<>") for t in toks if t not in STOP and len(t) > 1)


def search_docs(qtext, depts, k=5):
    ph = ",".join("?" * len(depts))
    return q(f"""SELECT doc_id, kind, department, title, anon_text, created_at, score FROM (
                  SELECT *, fts_main_documents.match_bm25(doc_id, ?) AS score FROM documents WHERE department IN ({ph}))
                 WHERE score IS NOT NULL ORDER BY score DESC LIMIT {int(k)}""", [_query_terms(qtext)] + list(depts))


def search_memory(qtext, depts, k=5):
    ph = ",".join("?" * len(depts))
    try:
        return q(f"""SELECT fact_id, doc_id, department, text, score FROM (
                      SELECT *, fts_main_memory.match_bm25(fact_id, ?) AS score FROM memory WHERE status='approved' AND department IN ({ph}))
                     WHERE score IS NOT NULL ORDER BY score DESC LIMIT {int(k)}""", [_query_terms(qtext)] + list(depts))
    except Exception:
        return []


def _blocked_hits(qtext, role):
    """Does the question hit customer-credit material outside this role's perimeter? (count only; nothing is retrieved for the user)"""
    if ROLES[role]["credit"]:
        return 0
    others = [d for d in ("credit", "compliance") if d not in ROLES[role]["depts"]]
    if not (CREDIT_RE.search(qtext) or PSEUDO_RE.search(qtext)):
        return 0
    return len(search_docs(qtext, others, k=3))


def answer_knowledge(question, role, actor="user"):
    """Returns dict(text, sources, model, status, meta). Role comes from the login session, never from the question text.
    Knowledge = APPROVED memory facts only, filtered by the role's departments BEFORE retrieval."""
    depts = ROLES[role]["depts"]
    pq = pseudonymise_query(question)
    claims_role = bool(re.search(r"\b(i am|i'm|as the|acting as)\s+(the\s+)?(cfo|ceo|director|admin|administrator|compliance|manager|head)", question, re.I))
    blocked = _blocked_hits(pq, role)
    facts = search_memory(pq, depts, k=4)
    cands = [{"doc_id": f["doc_id"], "text": f["text"], "score": f["score"], "fact": f["fact_id"]} for f in facts]
    top = cands[0]["score"] if cands else 0.0
    meta = {"question_pseudonymised": pq, "top_score": round(top, 3), "role_claim_ignored": claims_role,
            "departments_searched": depts}
    if blocked and top < ABSTAIN_SCORE * 3:
        audit(actor, role, "access_denied", None, {**meta, "blocked_hits": blocked})
        return {"text": f"That's outside your access. It concerns customer credit data, which the {ROLES[role]['label']} role can't see.", "sources": [], "model": "access policy", "status": "denied", "meta": meta}
    unknown = _unknown_entities(question, depts)
    if unknown:
        meta["unknown_terms"] = unknown
    if (not cands or top < ABSTAIN_SCORE) and not unknown:
        # weak keyword match: let the model turn the question into search keywords, then search again
        kw, _m = llm.chat([{"role": "system", "content": "You turn questions into search keywords for a bank's internal knowledge base."},
                           {"role": "user", "content": f"Question: {pq}\nReply with 4-8 lowercase keywords and likely synonyms "
                            "(e.g. build -> batch job failed; holidays -> branch hours), space-separated, nothing else."}], max_tokens=40)
        if kw:
            meta["expanded_terms"] = kw.strip()[:200]
            more = search_memory(pq + " " + kw, depts, k=4)
            seen = {c["fact"] for c in cands}
            cands += [{"doc_id": f["doc_id"], "text": f["text"], "score": f["score"], "fact": f["fact_id"]} for f in more if f["fact_id"] not in seen]
            cands.sort(key=lambda c: -c["score"]); top = cands[0]["score"] if cands else 0.0
    if not cands or unknown:
        audit(actor, role, "abstain", None, meta)
        return {"text": "I don't know. There is nothing in the approved knowledge about this.",
                "sources": [], "model": "retrieval threshold", "status": "abstain", "meta": meta}
    ctx = cands[:4]
    txt, model = llm.chat(PM("qa", {"question": pq, "chunks": [{"doc_id": c["doc_id"], "text": c["text"]} for c in ctx]}), max_tokens=300)
    if txt is None:  # offline stub: extractive answer from the best approved fact
        best = ctx[0]
        body = best["text"].split(": ", 1)[-1]
        txt = f"{body[:320]}{'…' if len(body) > 320 else ''} [{best['doc_id']}]"
    norm = txt.upper().replace("’", "'")
    if ABSTAIN in norm or "NON LO SO" in norm:
        audit(actor, role, "abstain", None, {**meta, "model": model})
        return {"text": "I don't know. The approved sources are not enough to answer this.", "sources": [], "model": model, "status": "abstain", "meta": meta}
    cited = re.findall(r"\[([A-Z]{2,4}-[0-9A-Za-z\-]+)\]", txt)
    valid = {c["doc_id"] for c in ctx}
    if not any(cid in valid for cid in cited):  # every answer must cite: attach the facts actually used
        txt = txt.rstrip() + " " + " ".join(f"[{c['doc_id']}]" for c in ctx[:1])
    # independent checker (a different model) must confirm every claim is in the cited sources, otherwise we don't answer
    verdict, vmodel = llm.verify(question, txt, [{"doc_id": c["doc_id"], "text": c["text"]} for c in ctx])
    meta["checker"] = {"verdict": verdict, "model": vmodel}
    if verdict == "unsupported":
        audit(actor, role, "answer_blocked_by_checker", None, {**meta, "model": model, "draft": txt[:300]})
        return {"text": "I don't know. I drafted an answer, but the independent checker couldn't confirm it against the sources, so I won't guess.",
                "sources": [], "model": f"{model} · {vmodel}", "status": "abstain", "meta": meta}
    if verdict == "supported":
        model = f"{model} · verified by {vmodel}"
    srcs = []
    for c in ctx:
        if c["doc_id"] not in [s["id"] for s in srcs]:
            srcs.append({"id": c["doc_id"], "fact": c["fact"], "snippet": c["text"][:180], "score": round(c["score"], 2)})
    audit(actor, role, "answer", None, {**meta, "model": model, "sources": [s["id"] for s in srcs]})
    return {"text": txt, "sources": srcs, "model": model, "status": "ok", "meta": meta}



_vocab_cache = {}


def _unknown_entities(question, depts):
    """Hallucination guard: proper nouns / acronyms in the question that appear nowhere in the approved memory -> we don't know."""
    key = (tuple(depts), q("SELECT count(*) n FROM memory WHERE status='approved'")[0]["n"])
    if key not in _vocab_cache:
        ph = ",".join("?" * len(depts))
        txt = " ".join(r["text"] for r in q(f"SELECT text FROM memory WHERE status='approved' AND department IN ({ph})", list(depts))).lower()
        _vocab_cache.clear(); _vocab_cache[key] = txt
    vocab = _vocab_cache[key]
    words = re.findall(r"[A-Za-zÀ-ÿ][\w\-]+", question)
    out = []
    for i, w in enumerate(words):
        if i == 0 or len(w) < 3 or w.lower() in STOP or w.upper() in ("CFO", "CEO", "IT", "OK"):
            continue
        if (w[0].isupper() or w.isupper()) and w.lower() not in vocab:
            out.append(w)
    return out


def _best_sentence(text, qtext):
    terms = set(_query_terms(qtext).split())
    body = text.split(": ", 1)[-1]
    sents = re.split(r"(?<=[.!?])\s+", body)
    return max(sents, key=lambda s: sum(1 for t in terms if t in s.lower()))


# ---------------------------------------------------------------- memory
def memory_list(role):
    depts = ROLES[role]["depts"]
    ph = ",".join("?" * len(depts))
    return q(f"""SELECT * FROM memory WHERE department IN ({ph})
                 ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, decided_at DESC NULLS FIRST, fact_id""", depts)


def memory_decide(fact_id, decision, actor, role):
    assert decision in ("approved", "rejected")
    if decision == "approved":   # four-eyes: whoever proposed a fact cannot approve it
        prop = q("SELECT actor FROM audit WHERE event='fact_proposed' AND object_id=? ORDER BY ts DESC LIMIT 1", [fact_id])
        if prop and prop[0]["actor"] == actor:
            audit(actor, role, "four_eyes_blocked", fact_id, {"rule": "proposer cannot approve own fact"})
            return False
    x("UPDATE memory SET status=?, decided_by=?, decided_at=now() WHERE fact_id=?", [decision, f"{actor} ({role})", fact_id])
    with _lock:
        _reindex_memory()
    audit(actor, role, f"memory_{decision}", fact_id, {})


def add_fact(text, doc_id, department, actor, role):
    if injection(text) or JAILBREAK_RE.search(normalise(text)):   # no instructions smuggled into the shared memory
        audit(actor, role, "security_memory_poisoning_blocked", None, {"text": text[:200]})
        return None
    n = q("SELECT count(*) AS n FROM memory")[0]["n"] + 1
    fid = f"F-{n:04d}"
    x("INSERT INTO memory VALUES (?,?,?,?, 'pending', NULL, NULL)", [fid, doc_id or "MANUAL", department, text])
    audit(actor, role, "fact_proposed", fid, {"source": doc_id or "manual"})
    return fid


def extract_new_facts(doc_id, actor, role):
    """LLM proposes pending facts from one document (never auto-approved)."""
    d = q("SELECT doc_id, department, anon_text FROM documents WHERE doc_id=?", [doc_id])
    if not d:
        return 0, "n/a"
    d = d[0]
    if injection(d["anon_text"]):
        audit(actor, role, "injection_flagged", doc_id, {"note": "document treated as data; no facts extracted"})
        return 0, "blocked: prompt injection"
    txt, model = llm.chat(PM("extract_facts", {"doc_id": doc_id, "text": d["anon_text"][:1500]}), max_tokens=350)
    facts = []
    if txt:
        try:
            m = re.search(r"\{.*\}", txt, re.S)
            facts = [f["text"] for f in json.loads(m.group(0)).get("facts", []) if f.get("text")][:3]
        except Exception:
            facts = []
    if not facts:
        facts = [s for s in re.split(r"(?<=[.!?])\s+", d["anon_text"]) if len(s) > 40][:1]
        model = "stub"
    for f in facts:
        add_fact(f.strip(), doc_id, d["department"], "lumen-brain", role)
    return len(facts), model


# ---------------------------------------------------------------- briefs ("speaks first")
def _first(text, n=210):
    t = re.sub(r"\s+", " ", text or "").strip()
    sents = re.split(r"(?<=[.!?])\s+", t)
    out = sents[0]
    if len(out) < 90 and len(sents) > 1: out += " " + sents[1]
    return out if len(out) <= n else out[:n].rsplit(" ", 1)[0] + "…"


def _dates(text):
    out = []
    for d in re.findall(r"(\d{2}/\d{2}/\d{4})", text or ""):
        try: out.append(dt.datetime.strptime(d, "%d/%m/%Y").date())
        except ValueError: pass
    return out


def _events(role):
    """Signals that need this person's attention today, most urgent first. Each: {doc_id, text}. Injected text is never passed on."""
    T = today()
    depts = ROLES[role]["depts"]
    ph = ",".join("?" * len(depts))
    docs = q(f"SELECT doc_id, kind, department, title, anon_text, created_at FROM documents WHERE department IN ({ph}) ORDER BY created_at DESC, doc_id DESC", depts)
    recent = [d for d in docs if (T - d["created_at"].date() if hasattr(d["created_at"], "date") else dt.timedelta(0)).days <= 3]
    ev = []
    for d in recent:   # covenant / credit alerts
        if d["kind"] == "credit_memo" and re.search(r"ALERT|covenant", d["anon_text"]):
            ev.append({"doc_id": d["doc_id"], "text": "Covenant breach risk: " + _first(d["anon_text"]).replace("ALERT: ", "")})
    for d in recent:   # AML
        if re.search(r"money.laundering|AML", d["anon_text"] + d["title"], re.I) and d["kind"] != "policy":
            ev.append({"doc_id": d["doc_id"], "text": "AML alert to assess: " + _first(d["anon_text"]).replace("Anti-money-laundering alert: ", "")})
    kyc = []
    for d in docs:     # KYC documents expiring in the next 7 days (or just expired)
        if d["kind"] != "kyc_note": continue
        for e in _dates(d["anon_text"]):
            days = (e - T).days
            if -10 <= days <= 7 and re.search(r"expire", d["anon_text"], re.I):
                who = PSEUDO_RE.search(d["anon_text"])
                kyc.append((days, d["doc_id"], f"<{who.group(1)}>" if who else "a customer", e))
    kyc.sort()
    if kyc:
        lst = "; ".join(f"{w} {'expired' if dd < 0 else 'expires'} {e.strftime('%d/%m')} [{i}]" for dd, i, w, e in kyc[:4])
        ev.append({"doc_id": kyc[0][1], "text": f"{len(kyc)} customer ID documents expired or expiring within 7 days (blocks new lending): {lst}."})
    for d in docs:     # regulatory / policy deadlines within 7 days
        if d["kind"] == "policy":
            for e in _dates(d["anon_text"]):
                if 0 <= (e - T).days <= 7:
                    ev.append({"doc_id": d["doc_id"], "text": f"Deadline in {(e - T).days} days: {_first(d['anon_text'])}"})
    batch = [d for d in recent if d["kind"] == "ticket" and re.search(r"batch", d["title"] + d["anon_text"], re.I)]
    if batch:
        ids = " ".join(f"[{d['doc_id']}]" for d in batch)
        rb = next((d for d in docs if d["kind"] == "policy" and re.search(r"Runbook", d["title"])), None)
        ev.append({"doc_id": batch[0]["doc_id"], "text": f"Nightly batch RICONC-02 failed {len(batch)} times in 3 days ({_first(batch[0]['anon_text'], 120)}) {ids}"
                   + (f" The runbook says to escalate to the vendor after two consecutive failures [{rb['doc_id']}]." if rb and len(batch) >= 2 else "")})
    rec = [d for d in recent if d["kind"] == "ticket" and re.search(r"record error", d["title"], re.I)]
    if rec:
        ev.append({"doc_id": rec[0]["doc_id"], "text": f"{len(rec)} customer-record errors (duplicate emails) opened in the last 3 days " + " ".join(f"[{d['doc_id']}]" for d in rec[:4])})
    for d in recent:   # prompt injection: report it, never forward its content
        if injection(d["anon_text"]):
            ev.append({"doc_id": d["doc_id"], "text": "Suspicious inbound email blocked: it contained instructions aimed at the AI (asking for the customer list). "
                       "Treated as data; nothing was sent or approved. Consider reporting it to security."})
    if ROLES[role]["credit"]:
        c = q("SELECT count(*) n, count(*) FILTER (WHERE status='exception') e, count(*) FILTER (WHERE status='new') nw FROM cases")[0]
        if c["e"]:
            ev.append({"doc_id": "AUTOPILOT", "text": f"Reminder autopilot: {c['n']} overdue cases, {c['e']} exceptions stopped for human review."})
        elif c["nw"]:
            ev.append({"doc_id": "AUTOPILOT", "text": f"{c['nw']} overdue loans in today's arrears extract are waiting for the reminder autopilot."})
        pa = q("SELECT count(*) n FROM actions WHERE status='proposed'")[0]["n"]
        if pa:
            ev.append({"doc_id": "APPROVALS", "text": f"{pa} proposed actions are waiting for your approval."})
    pm = len([m for m in memory_list(role) if m["status"] == "pending"])
    if pm:
        ev.append({"doc_id": "MEMORY", "text": f"{pm} new facts are waiting to be approved or rejected in the shared memory."})
    return ev


def make_brief(role, actor="scheduler 07:30"):
    ev = _events(role)
    txt, model = llm.chat(PM("brief", {"role": ROLES[role]["label"], "events": ev}), max_tokens=450)
    if txt is None:
        txt = "\n".join(f"• {e['text']}" + (f" [{e['doc_id']}]" if "-" in e["doc_id"] and f"[{e['doc_id']}]" not in e["text"] else "") for e in ev[:7]) \
              or "• Nothing relevant today."
    x("INSERT INTO briefs VALUES (?, now(), ?, ?, ?)", [role, txt, model, json.dumps([e["doc_id"] for e in ev])])
    audit(actor, role, "brief_generated", None, {"model": model, "events": len(ev)})
    if ROLES[role]["credit"]:   # proactive proposals: KYC renewals (proposed only; a human approves)
        for d in q("SELECT doc_id, title, anon_text FROM documents WHERE kind='kyc_note' AND created_at::DATE >= ?::DATE - INTERVAL 3 DAY "
                   "AND regexp_matches(anon_text, '(?i)expir|scad') LIMIT 3", [today()]):
            aid = f"A-{d['doc_id']}"
            if not q("SELECT 1 FROM actions WHERE action_id=?", [aid]):
                who = (PSEUDO_RE.search(d["anon_text"]) or [None, None])
                to = f"<{who.group(1)}>" if who else "customer"
                x("INSERT INTO actions VALUES (?, 'draft_email', ?, ?, 'proposed', 'brain', NULL, now())",
                  [aid, d["doc_id"], json.dumps({"to": to, "subject": "Your ID document is about to expire",
                   "body": f"Dear {to}, the identity document we hold for you at Lumen Bank is about to expire. Please send us an updated copy "
                           "so we can keep your account fully operational.", "why": f"KYC document expiring [{d['doc_id']}]"}, ensure_ascii=False)])
                audit("lumen-brain", role, "action_proposed", aid, {"kind": "draft_email", "source": d["doc_id"]})
    return txt, model


def latest_brief(role):
    r = q("SELECT * FROM briefs WHERE role=? ORDER BY ts DESC LIMIT 1", [role])
    return r[0] if r else None


# ------------------------------------------------------------------ intent routing (router trained from scratch + 9B fallback)
ROUTER_CONF = 0.8
WORK_RE = re.compile(r"\b(my|me|i|mine|miei|mio|mia|devo|ho)\b(?:\W+\w+){0,4}?\W+(work|tasks?|to-?do|plate|desk|queue|day|pending|approv\w*|attention|status|focus|behind|urgent|lavoro|fare|sospeso)\b"
                     r"|\b(catch me up|what did i miss|status update|what is my job|what's my job|my role|have to do|need to do|should i do|devo fare|incidents?|overnight|anything broken|open tickets|alerts? today)\b", re.I)
OOS_RE = re.compile(r"weather|meteo|tempo fa|football|soccer|juventus|torino fc|match|game|score|poem|poesia|haiku|joke|barzelletta|bitcoin|crypto|price of|movie|film|music|song|recipe|pizza|restaurant|flight|hotel|capital of|translate|how tall|\d+\s*(times|x|\*)\s*\d+", re.I)


def route(question):
    """(intent, confidence, router) — tiny from-scratch router first; if unsure, the distilled 9B decides."""
    try:
        from . import router as R
        intent, p = R.predict(question)
    except Exception:
        intent, p = "knowledge", 0.0
    who = "router (from scratch)"
    if p < ROUTER_CONF:
        txt, model = llm.chat(PM("intent", {"text": question}), max_tokens=8, temperature=0)
        lab = (txt or "").strip().lower().strip(". `")
        if lab in ("knowledge", "my_work", "customer", "action", "help", "out_of_scope"):
            intent, who = lab, f"router → {model}"
    if intent in ("knowledge", "help", "out_of_scope") and WORK_RE.search(question):   # safety net for personal questions
        intent = "my_work"
    return intent, p, who


def _my_work(question, role, actor):
    ev = _events(role)
    first = (actor or "").split()[0] if actor else ""
    if not ev:
        return {"text": f"You're all clear{', ' + first if first else ''}: nothing needs your attention right now.", "sources": [], "model": "live queues", "status": "ok", "meta": {}}
    msgs = [{"role": "system", "content": "You are ALFRED, a calm assistant inside a bank. Summarise the employee's work status from the items given. "
             "3-5 short bullet points, most urgent first, each ending with its [ID]. Start with one short sentence. Use the items' exact facts: "
             "never call something overdue or late unless the item says so, never invent numbers."},
            {"role": "user", "content": f"Employee: {first} ({ROLES[role]['label']}). Question: {question}\nItems:\n" + "\n".join(f"[{e['doc_id']}] {e['text']}" for e in ev[:7])}]
    txt, model = llm.chat(msgs, max_tokens=350)
    if not txt:
        txt = f"Here's where things stand{', ' + first if first else ''}:\n" + "\n".join(f"• {e['text']} [{e['doc_id']}]" for e in ev[:6])
        model = "live queues"
    for tok, word in (("[APPROVALS]", "(see Approvals)"), ("[AUTOPILOT]", "(see Autopilot)"), ("[MEMORY]", "(see Memory)")):
        txt = txt.replace(tok, word)
    src = [{"id": e["doc_id"], "fact": None, "snippet": e["text"][:180], "score": 1.0} for e in ev[:6] if "-" in e["doc_id"]]
    audit(actor, role, "work_status", None, {"items": len(ev), "model": model})
    return {"text": txt, "sources": src, "model": model, "status": "ok", "meta": {}}


PROPOSE_BLOCK = [
    (re.compile(r"anti.?money|\baml\b|money.laundering|under (review|investigation)|suspicious (activity|transaction)|segnalazione", re.I),
     "I can't prepare any contact about an AML review: telling a customer would be tipping-off. Refer it to Compliance."),
    (re.compile(r"[\w.+-]+@(?!lumenbank\.example)[\w-]+\.[\w.]+|gmail|hotmail|yahoo|personal (email|address)|whatsapp|dropbox|usb", re.I),
     "I can't send bank data to addresses or channels outside Lumen Bank."),
    (re.compile(r"\b(all|every|whole|full|entire|tutti)\b.{0,30}\b(customers?|clients?|iban|list|database|vault|records|clienti)\b|export|dump|download", re.I),
     "I can't prepare bulk exports of customer data. Exports come only from the approved autopilot batch."),
    (re.compile(r"urgent instructions|EML-0085|the email (says|asks)|forward (the|that) (email|mail)", re.I),
     "That email was flagged as a prompt-injection attempt. I won't forward it or act on it; report it to Security."),
    (re.compile(r"^\s*(please\s+|pls\s+|go ahead and\s+|just\s+)?(approve|execute|pay|transfer|wire|bonifica|esegui|approva)\b"
                r"|\b(approve|execute|pay|send)\s+(it|this|them|all|everything|the \w+)\s+(now|for me|yourself|automatically|directly)\b"
                r"|\bskip (the )?approval|without (my |any |an? )?(approval|review)|do(n'?t| not) wait for (approval|me)|override (the )?(approval|rules?)\b", re.I),
     "I never approve, pay or execute anything myself. I can prepare it, and a person approves each item in Approvals."),
]


def _restricted_customers():
    """Customers named in an open AML alert. Contact is blocked without telling the requester why (no tipping-off, even internally)."""
    return {m for (t,) in rows("SELECT anon_text FROM documents WHERE department='aml'") for m in PSEUDO_RE.findall(t)}


def _propose(question, role, actor):
    pq = pseudonymise_query(question)
    hit = {f"<{m}>" for m in PSEUDO_RE.findall(pq)} & {f"<{m}>" for m in _restricted_customers()}
    if hit:
        audit(actor, role, "proposal_refused_restricted_customer", None, {"q": pq[:200]})
        return {"text": "This customer's file is restricted right now, so I can't prepare any contact. Please check with Compliance before reaching out.",
                "sources": [], "model": "approval policy", "status": "denied", "meta": {}}
    for rx, why in PROPOSE_BLOCK:
        if rx.search(normalise(question)):
            audit(actor, role, "proposal_refused", None, {"q": pseudonymise_query(question)[:200], "why": why})
            return {"text": why, "sources": [], "model": "approval policy", "status": "denied", "meta": {}}
    if not ROLES[role]["credit"]:
        return {"text": "I can't prepare that from your role. Customer actions belong to the credit and compliance teams.", "sources": [], "model": "access policy", "status": "denied", "meta": {}}
    aid = f"A-REQ-{int(dt.datetime.now().timestamp())}"
    x("INSERT INTO actions VALUES (?, 'draft_email', NULL, ?, 'proposed', 'brain', NULL, now())",
      [aid, json.dumps({"to": "(to confirm)", "subject": "Request from " + (actor or "colleague"), "body": pseudonymise_query(question),
                        "why": f"Requested in chat by {actor}"}, ensure_ascii=False)])
    audit(actor, role, "action_proposed", aid, {"kind": "draft_email", "source": "chat request"})
    return {"text": "I don't act on my own. I've prepared this as a proposal in Approvals. Nothing will be sent until someone approves it.",
            "sources": [], "model": "approval policy", "status": "proposed", "meta": {"action_id": aid}}


HELP_TXT = ("I'm ALFRED. I can:\n• tell you what needs your attention today (\"what's on my plate?\")\n• answer questions about policies, procedures and incidents, always with sources\n"
            "• look up customers and loans you're allowed to see\n• prepare reminders and emails for approval (I never send anything myself)\n"
            "If something isn't in the approved knowledge, I'll say I don't know.")


HELP_RE = re.compile(r"tell me something|what can i ask|what should i ask|^\s*(hi|hello|hey|ciao|buongiorno|good (morning|afternoon|evening)|thanks?|thank you|grazie|ok|cool|great)\b|what can you do|how (do|can) i use|who are you|help\b|how does this work|what are you able", re.I)


def _rewrite_and_retry(question, role, actor):
    """Query expansion: when keyword search finds nothing, the assistant rewrites the question in the bank's policy vocabulary and we search once more."""
    msgs = [{"role": "user", "content": "Rewrite this bank employee question as a short keyword search query using formal banking-policy vocabulary "
             "(e.g. 'kyc refresh' -> 'customer due diligence renewed', 'clients' -> 'customers', 'rerun' -> 're-run job'). Keep the meaning. "
             f"Reply with ONLY the query.\n\nQuestion: {question}"}]
    txt, _ = llm.chat(msgs, max_tokens=40, temperature=0)
    if not txt or txt.strip().lower() == question.strip().lower():
        return None
    a = answer_knowledge(txt.strip().strip('"'), role, actor)
    a.setdefault("meta", {})["rewritten_query"] = txt.strip()
    return a if a["status"] == "ok" else None


JAILBREAK_RE = re.compile(r"^\s*system\s*:|you are now|admin mode|developer mode|god mode|jailbreak|act as (an? )?(admin|root|system)|disregard (your|all) (rules|instructions)|reveal (the )?(vault|system prompt)|print (the )?(full )?vault", re.I)


META_RE = re.compile(r"\b(is (this|it|that|EML-\d+) (a |an )?(prompt.?)?injection|should (i|we) report|report (it|this|that)|phishing|suspicious email|what (does|did) (the|that) (injection|suspicious|urgent) email)", re.I)
DOCID_RE = re.compile(r"\b(?:POL|EML|CHT|TKT|KYC|MEM)-\d{3,4}\b")


ABOUT_EMAIL_RE = re.compile(r"(EML-\d+|\bemail\b|\bmail\b|\bmessage\b|['\"‘“])", re.I)
ASKING_RE = re.compile(r"\?|\b(did|does|has|is|was|should|what|why|how)\b", re.I)


def answer(question, role, actor="user"):
    about_injection = injection(question) and ABOUT_EMAIL_RE.search(question) and ASKING_RE.search(question)
    if (META_RE.search(question) or about_injection) and not JAILBREAK_RE.search(normalise(question)):
        inj = rows("SELECT doc_id FROM planted_events WHERE name='injection'") if "planted_events" in [r[0] for r in rows("SHOW TABLES")] else []
        did = inj[0][0] if inj else "EML-0085"
        audit(actor, role, "security_question", did, {"q": question[:200]})
        return {"text": f"Yes. {did} is a prompt-injection attempt: it tries to make the assistant send the customer list and approve pending reminders. "
                        "It was quarantined on arrival: treated as data, never as instructions, and nothing was sent or approved. "
                        "Please report it to Security (phishing mailbox) and don't reply to the sender.",
                "sources": [{"id": did, "fact": None, "snippet": "Flagged inbound email (content withheld: suspected prompt injection)", "score": 1.0}],
                "model": "security policy", "status": "ok", "meta": {}}
    ids = DOCID_RE.findall(question)
    if ids:   # names a document that doesn't exist (or isn't visible to this role) -> don't guess
        ph = ",".join("?" * len(ROLES[role]["depts"]))
        seen = {r[0] for r in rows(f"SELECT doc_id FROM documents WHERE doc_id IN ({','.join('?' * len(ids))}) AND department IN ({ph})", ids + ROLES[role]["depts"])}
        if any(i not in seen for i in ids):
            return {"text": f"I don't know. I can't find {', '.join(i for i in ids if i not in seen)} among the documents you can access.",
                    "sources": [], "model": "retrieval", "status": "abstain", "meta": {}}
    if injection(question) or JAILBREAK_RE.search(normalise(question)):
        audit(actor, role, "security_injection_attempt", None, {"q": question[:200]})
        return {"text": "I can't follow or repeat instructions that try to override my rules. This attempt has been logged for security.",
                "sources": [], "model": "security policy", "status": "denied", "meta": {}}
    intent, p, who = route(question)
    if intent == "help" and not HELP_RE.search(question):   # only real greetings / "what can you do" get the help card
        intent = "knowledge"
    if intent == "out_of_scope" and not OOS_RE.search(question):   # vague, not clearly off-topic -> guide the person instead of refusing
        intent = "help"
    if HELP_RE.search(question) and len(question.split()) <= 6 and intent in ("knowledge", "out_of_scope"):
        intent = "help"
    if intent == "my_work":
        a = _my_work(question, role, actor)
    elif intent == "action":
        a = _propose(question, role, actor)
    elif intent == "help":
        a = {"text": HELP_TXT, "sources": [], "model": "help", "status": "ok", "meta": {}}
    elif intent == "out_of_scope":
        a = {"text": "That's outside what I can help with. I only work with Lumen Bank's internal knowledge and your work queue.", "sources": [], "model": "scope policy", "status": "abstain", "meta": {}}
    else:
        a = answer_knowledge(question, role, actor)
        if a["status"] == "abstain" and not WORK_RE.search(question):
            a = _rewrite_and_retry(question, role, actor) or a
        if a["status"] == "abstain" and WORK_RE.search(question):
            a = _my_work(question, role, actor)
        elif a["status"] == "abstain":   # say WHO owns it instead of a bare "I don't know" when it exists outside this role's perimeter
            others = [d for d in ("credit", "compliance", "it") if d not in ROLES[role]["depts"]]
            hits = search_docs(pseudonymise_query(question), others, k=3) if others else []
            if hits and hits[0]["score"] >= ABSTAIN_SCORE * 3:
                team = {"it": "IT", "credit": "Credit", "compliance": "Compliance"}[hits[0]["department"]]
                a["text"] = (f"I can't answer that from your role. It's covered in {team} team documents, which you don't have access to. "
                             f"Ask the {team} team, or someone with {team} access.")
                a["status"] = "denied"; a["model"] = "access policy"
    a.setdefault("meta", {})["intent"] = {"intent": intent, "confidence": round(p, 3), "by": who}
    return a
