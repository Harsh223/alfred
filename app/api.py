import os
"""ALFRED public REST API (/v1): Agentic Ledger For Regulated Enterprise Decisions, on top of the Lumen Bank brain + autopilot.

Security model (same as the web app):
- Every call carries `X-API-Key`. The key maps to a role (rm_credit, it_support, compliance). The role ALWAYS comes from the key,
  never from the request body or the question text.
- The API never re-identifies: answers, cases and actions carry pseudonyms (<CLIENT_0042>), not real values.
- Irreversible actions need `X-Human-Approval: true`: an API client must show the action to a person and send it only after that
  person approved. Agents must never set it on their own. Four-eyes rules from the core still apply.
- Per-key rate limit (default 60 requests / minute) and an `api_call` audit event for every request.
Keys: env ALFRED_API_KEYS='{"key": "role", ...}', otherwise runs/.api_keys.json (demo keys, created at startup, chmod 600).
"""
import glob, hashlib, hmac, json, os, secrets, threading, time
from collections import deque
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from brain import core as C
from brain import llm
from autopilot import engine as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS_FILE = os.path.join(ROOT, "runs", ".api_keys.json")
RATE = int(os.environ.get("ALFRED_API_RATE", "60"))          # requests per key per window
WINDOW = 60.0
VERSION = "1.0.0"
TITLE = "ALFRED API"
DESCRIPTION = """**ALFRED: Agentic Ledger For Regulated Enterprise Decisions.** Company Brain + overdue-loan Autopilot of *Lumen Bank* (fictional, Turin; synthetic data only).

**Auth:** send `X-API-Key: <key>`. The key decides your role (`rm_credit`, `it_support`, `compliance`); a role in the body or in the question is ignored.

**Privacy:** the API never re-identifies. Customers appear as pseudonyms such as `<CLIENT_0042>`.

**Human approval:** `POST /v1/actions/{id}/decision` needs `X-Human-Approval: true`. Your client must show the action to a person and send the header only after that person approves. **Agents must never set it automatically.** Four-eyes: whoever proposed something cannot approve it.

**Limits:** 60 requests per minute per key (`429` with `Retry-After`). Every call is written to the audit trail (`api_call`).

**Errors:** `{"error": {"code": "...", "message": "..."}}` with 401 (bad or missing key), 403 (role not allowed), 404, 409 (four-eyes or not pending), 422 (invalid body or blocked content), 428 (human approval header missing), 429 (rate limit). Full guide: `docs/API.md`."""


# ------------------------------------------------------------------ keys
def _load_keys():
    raw = os.environ.get("ALFRED_API_KEYS")
    if raw:
        try:
            keys = json.loads(raw)
        except Exception:
            keys = {}
    else:
        if not os.path.exists(KEYS_FILE):
            os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
            demo = {f"alf_{r.split('_')[0]}_{secrets.token_urlsafe(18)}": r for r in ("rm_credit", "rm_credit", "it_support", "compliance")}
            fd = os.open(KEYS_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(demo, f, indent=1)
        os.chmod(KEYS_FILE, 0o600)
        keys = json.load(open(KEYS_FILE))
    return {k: r for k, r in keys.items() if isinstance(k, str) and len(k) >= 16 and r in C.ROLES}


KEYS = _load_keys()
EXTRA_KEYS = {}        # sha256(key) -> (role, team): arena team keys (app/arena.py), only hashes are kept
EXTRA_ROUTERS = []     # extra routers documented in the OpenAPI schema (arena)


def key_id(key):
    return hashlib.sha256(key.encode()).hexdigest()[:10]


class Principal(BaseModel):
    role: str
    key_id: str
    team: Optional[str] = None

    @property
    def actor(self):
        return f"api-client {self.key_id}"


class APIError(Exception):
    def __init__(self, status, code, message, headers=None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


_hits = {}
_hits_lock = threading.Lock()


def _rate(kid):
    now = time.time()
    with _hits_lock:
        dq = _hits.setdefault(kid, deque())
        while dq and dq[0] <= now - WINDOW:
            dq.popleft()
        if len(dq) >= RATE:
            return False, 0, int(dq[0] + WINDOW - now) + 1
        dq.append(now)
        return True, RATE - len(dq), 0


_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="Your ALFRED API key. It decides your role.")


def principal(request: Request, key: Optional[str] = Depends(_scheme)) -> Principal:
    role, team = None, None
    if key:
        for k, r in KEYS.items():          # constant-time compare against every key
            if hmac.compare_digest(k.encode(), key.encode()):
                role = r
        if not role and EXTRA_KEYS:
            ent = EXTRA_KEYS.get(hashlib.sha256(key.encode()).hexdigest())
            if ent:
                role, team = ent
    if not role:
        raise APIError(401, "invalid_api_key", "Missing or invalid X-API-Key.")
    p = Principal(role=role, key_id=key_id(key), team=team)
    request.state.principal = p
    ok, left, retry = _rate(p.key_id)
    request.state.rate_left = left
    if not ok:
        raise APIError(429, "rate_limited", f"More than {RATE} requests per minute for this key. Retry in {retry}s.", {"Retry-After": str(retry)})
    return p


def credit_only(p: Principal = Depends(principal)) -> Principal:
    if not C.ROLES[p.role]["credit"]:
        C.audit(p.actor, p.role, "access_denied", None, {"via": "api", "rule": "customer credit data"})
        raise APIError(403, "forbidden_for_role", f"Not available for the {C.ROLES[p.role]['label']} role: customer credit data.")
    return p


ERR = {"description": "Error", "content": {"application/json": {"example": {"error": {"code": "forbidden_for_role", "message": "Not available for your role."}}}}}
ERRS = {401: ERR, 403: ERR, 429: ERR}
router = APIRouter(prefix="/v1", responses={401: ERR, 429: ERR})


# ------------------------------------------------------------------ models
class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")    # a "role" field in the body is silently ignored: the key decides


class AskIn(_In):
    question: str = Field(..., min_length=1, max_length=800, description="Question in English or Italian.",
                          examples=["What is the SME credit limit without committee approval?"])


class Source(BaseModel):
    id: str = Field(description="Document id, e.g. POL-0002")
    fact: Optional[str] = Field(None, description="Approved memory fact used")
    snippet: str = Field("", description="Pseudonymised snippet")
    score: Optional[float] = None


class AskOut(BaseModel):
    answer: str = Field(description="Answer with [DOC-ID] citations. Pseudonyms stay masked.")
    status: Literal["ok", "abstain", "denied", "proposed"] = Field(description="ok = answered from approved sources; abstain = 'I don't know'; denied = outside your role; proposed = an action was prepared for human approval")
    sources: List[Source] = []
    model: str = Field(description="Model chain that produced the answer")
    checker: Optional[dict] = Field(None, description="Independent checker verdict, if it ran")
    intent: Optional[dict] = Field(None, description="Router intent, confidence and which router decided")
    action_id: Optional[str] = Field(None, description="Set when status=proposed: the action now waiting in /v1/actions")
    role: str = Field(description="Role taken from your API key")
    model_config = ConfigDict(json_schema_extra={"examples": [{"answer": "Up to EUR 250,000 without credit-committee approval [POL-0002].", "status": "ok",
        "sources": [{"id": "POL-0002", "fact": "F-0065", "snippet": "Credit Policy v3…", "score": 3.1}], "model": "student (1.2s) · verified by checker Qwen3.8-27B (0.4s)",
        "checker": {"verdict": "supported", "model": "checker Qwen3.8-27B"}, "intent": {"intent": "knowledge", "confidence": 0.97, "by": "router"}, "action_id": None, "role": "rm_credit"}]})


class BriefOut(BaseModel):
    role: str
    generated_at: Optional[str]
    model: Optional[str]
    text: str = Field(description="3-5 bullet morning brief with [DOC-ID] citations, pseudonymised")
    sources: List[str] = []


class TextIn(_In):
    text: str = Field(..., min_length=1, max_length=20000, examples=["Mario Rossi, IBAN IT60X0542811101000000123456, wrote from mario.rossi@example.com"])


class Entity(BaseModel):
    label: str
    start: int = Field(description="Offset in the masked text")
    end: int


class PseudoOut(BaseModel):
    text: str = Field(description="Masked text. No real value is ever returned.")
    entities: List[Entity]
    vault_matches: int = Field(description="Known customer identifiers replaced by their pseudonym (generic label for roles without re-identification rights)")
    layers: List[str]


class FactIn(_In):
    text: str = Field(..., min_length=5, max_length=600, examples=["Branches close at 13:00 on Christmas Eve."])


class Fact(BaseModel):
    fact_id: str
    doc_id: Optional[str]
    department: Optional[str]
    text: str
    status: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None


class DecisionIn(_In):
    decision: Literal["approved", "rejected"] = Field(..., examples=["approved"])


class Case(BaseModel):
    case_id: str
    customer: Optional[str] = Field(description="Customer pseudonym")
    days_past_due: Optional[int]
    amount_overdue: Optional[float]
    bucket: Optional[str]
    decision: Optional[str]
    exception: Optional[str]
    reason: Optional[str]
    status: Optional[str]


class Action(BaseModel):
    action_id: str
    kind: str
    case_id: Optional[str]
    payload: Any
    status: str
    proposed_by: Optional[str]
    approved_by: Optional[str]
    ts: Optional[str]


class AuditRow(BaseModel):
    ts: str
    actor: Optional[str]
    role: Optional[str]
    event: Optional[str]
    object_id: Optional[str]
    detail: Any


# ------------------------------------------------------------------ helpers
def _s(v):
    return None if v is None else str(v)


def _mask_vault(text, role):
    """Replace known identifiers with pseudonyms; for roles without re-identification rights, with a generic <LABEL> (no membership oracle)."""
    out = C.pseudonymise_query(text or "")
    n = 0
    v = C.vault()

    def sub(m):
        nonlocal n
        key = m.group(1)
        if key in v and ("<" + key + ">") not in (text or ""):
            n += 1
            return m.group(0) if C.ROLES[role]["reid"] else f"<{v[key][0]}>"
        return m.group(0)
    return C.PSEUDO_RE.sub(sub, out), n


def _fact(m):
    return Fact(fact_id=m["fact_id"], doc_id=m["doc_id"], department=m["department"], text=m["text"], status=m["status"],
                decided_by=m.get("decided_by"), decided_at=_s(m.get("decided_at")))


# ------------------------------------------------------------------ endpoints
@router.post("/ask", response_model=AskOut, tags=["Brain"], summary="Ask the Company Brain", responses=ERRS)
def ask(body: AskIn, p: Principal = Depends(principal)):
    """Answers only from **approved** memory, filtered by your role's departments before search, with `[DOC-ID]` citations.
    Says "I don't know" when no approved source covers the question. An independent checker model must confirm every claim.
    Requests for actions are only *proposed* (`status=proposed`, see `action_id`)."""
    a = C.answer(body.question, p.role, actor=p.actor)
    meta = a.get("meta") or {}
    return AskOut(answer=a["text"], status=a["status"] if a["status"] in ("ok", "abstain", "denied", "proposed") else "ok",
                  sources=[Source(id=s["id"], fact=s.get("fact"), snippet=s.get("snippet") or "", score=s.get("score")) for s in a.get("sources") or []],
                  model=a.get("model") or "", checker=meta.get("checker"), intent=meta.get("intent"), action_id=meta.get("action_id"), role=p.role)


@router.get("/brief", response_model=BriefOut, tags=["Brain"], summary="Today's morning brief for your role", responses=ERRS)
def brief(p: Principal = Depends(principal)):
    """The 07:30 brief the brain generated for your role without anyone asking (generated now if none exists yet)."""
    b = C.latest_brief(p.role)
    if not b:
        C.make_brief(p.role, actor=p.actor)
        b = C.latest_brief(p.role)
    try:
        srcs = [d for d in json.loads(b.get("sources") or "[]") if "-" in d]
    except Exception:
        srcs = []
    return BriefOut(role=p.role, generated_at=_s(b["ts"]), model=b.get("model"), text=b["text"], sources=srcs)


@router.post("/pseudonymise", response_model=PseudoOut, tags=["Privacy"], summary="Mask personal data in a text", responses=ERRS)
def pseudonymise(body: TextIn, p: Principal = Depends(principal)):
    """Masks personal data with the deterministic rules layer (IBAN mod-97, codice fiscale, P.IVA, CIE, cards with Luhn, e-mail, phone,
    Italian addresses, health terms) plus the bank's vault (known customers get their consistent pseudonym if your role may see them,
    otherwise a generic label). The fine-tuned GLiNER model is not loaded in this server, so unknown free-text names may pass:
    use this endpoint as a safety net, not as the only control. No real value is ever returned."""
    from anonymizer import pii
    text, n = _mask_vault(body.text, p.role)
    spans = sorted(pii.rules(text), key=lambda s: (s["start"], -(s["end"] - s["start"])))
    keep, last = [], -1
    for s in spans:
        if s["start"] >= last:
            keep.append(s); last = s["end"]
    out, ents, pos, shift = [], [], 0, 0
    for s in keep:
        out.append(text[pos:s["start"]])
        tag = f"<{s['label']}>"
        start = s["start"] + shift
        ents.append(Entity(label=s["label"], start=start, end=start + len(tag)))
        out.append(tag)
        shift += len(tag) - (s["end"] - s["start"])
        pos = s["end"]
    out.append(text[pos:])
    C.audit(p.actor, p.role, "api_pseudonymise", None, {"chars": len(body.text), "entities": len(ents), "vault_matches": n})
    return PseudoOut(text="".join(out), entities=ents, vault_matches=n, layers=["vault", "rules (IBAN mod-97, CF, P.IVA, CIE, Luhn, email, phone, address, health)"])


@router.get("/memory", response_model=List[Fact], tags=["Memory"], summary="List memory facts your role can see", responses=ERRS)
def memory_list(status: Optional[Literal["pending", "approved", "rejected"]] = Query(None, description="Filter by status"),
                p: Principal = Depends(principal)):
    return [_fact(m) for m in C.memory_list(p.role) if not status or m["status"] == status]


@router.post("/memory", response_model=Fact, status_code=201, tags=["Memory"], summary="Propose a new fact (stays pending)", responses={**ERRS, 422: ERR})
def memory_add(body: FactIn, p: Principal = Depends(principal)):
    """The fact is pseudonymised and waits for a person to approve it. The brain never answers from pending facts.
    Text that looks like instructions to the AI is refused (`422 memory_poisoning_blocked`)."""
    fid = C.add_fact(C.pseudonymise_query(body.text.strip())[:600], "MANUAL", "credit" if C.ROLES[p.role]["credit"] else "it", p.actor, p.role)
    if not fid:
        raise APIError(422, "memory_poisoning_blocked", "The text looks like instructions to the AI and was not stored. The attempt was logged.")
    return _fact(C.q("SELECT * FROM memory WHERE fact_id=?", [fid])[0])


@router.post("/memory/{fact_id}/decision", response_model=Fact, tags=["Memory"], summary="Approve or reject a fact", responses={**ERRS, 404: ERR, 409: ERR})
def memory_decide(fact_id: str, body: DecisionIn, p: Principal = Depends(principal)):
    """Four-eyes: the key that proposed a fact cannot approve it (`409 four_eyes_blocked`). Only facts in your role's departments."""
    vis = {m["fact_id"]: m for m in C.memory_list(p.role)}
    if fact_id not in vis:
        raise APIError(404, "not_found", "No such fact in your role's departments.")
    if C.memory_decide(fact_id, body.decision, p.actor, p.role) is False:
        raise APIError(409, "four_eyes_blocked", "Whoever proposed a fact cannot approve it. Ask a colleague with a different key.")
    return _fact(C.q("SELECT * FROM memory WHERE fact_id=?", [fact_id])[0])


@router.post("/autopilot/run", tags=["Autopilot"], summary="Run today's overdue-loan reminders", responses=ERRS)
def autopilot_run(p: Principal = Depends(credit_only)):
    """Rules + distilled model triage every case of today's arrears extract. Exceptions stop for a person; send/fee/escalate are only
    *proposed* (see `/v1/actions`). Takes ~10-60 s with the live model. Returns the KPIs."""
    if p.team and os.environ.get("ARENA_PUBLIC") == "1":   # public arena: the autopilot runs on the operator's schedule, not on demand
        raise HTTPException(status_code=403, detail="On the public arena the autopilot runs on a schedule. Inspect /v1/autopilot/cases and /v1/actions instead.")
    return E.run(p.actor, p.role)


@router.get("/autopilot/cases", response_model=List[Case], tags=["Autopilot"], summary="Cases from the last run", responses=ERRS)
def autopilot_cases(status: Optional[Literal["new", "exception", "awaiting_approval", "held", "done"]] = Query(None),
                    p: Principal = Depends(credit_only)):
    rows = C.q("SELECT case_id, customer_id, days_past_due, amount_overdue, bucket, decision, exception, reason, status FROM cases "
               "WHERE (? IS NULL OR status = ?) ORDER BY case_id", [status, status])
    return [Case(customer=r.pop("customer_id"), **r) for r in rows]


@router.get("/autopilot/kpis", tags=["Autopilot"], summary="Autopilot KPIs and accuracy against gold labels", responses=ERRS)
def autopilot_kpis(p: Principal = Depends(credit_only)):
    return E.kpis()


@router.get("/actions", response_model=List[Action], tags=["Approvals"], summary="Proposed and decided actions", responses=ERRS)
def actions(status: Optional[Literal["proposed", "approved", "rejected", "executed"]] = Query(None), p: Principal = Depends(credit_only)):
    rows = C.q("SELECT * FROM actions WHERE (? IS NULL OR status = ?) ORDER BY action_id", [status, status])
    out = []
    for a in rows:
        try: pl = json.loads(a["payload"]) if isinstance(a["payload"], str) else a["payload"]
        except Exception: pl = a["payload"]
        out.append(Action(action_id=a["action_id"], kind=a["kind"], case_id=a["case_id"], payload=pl, status=a["status"],
                          proposed_by=a["proposed_by"], approved_by=a["approved_by"], ts=_s(a["ts"])))
    return out


@router.post("/actions/{action_id}/decision", tags=["Approvals"], summary="Approve or reject an action (human approval required)",
             responses={**ERRS, 404: ERR, 409: ERR, 428: ERR})
def action_decide(action_id: str, body: DecisionIn, p: Principal = Depends(credit_only),
                  x_human_approval: Optional[str] = Header(None, description="Must be `true`. Send it ONLY after a person saw and approved this action in your UI. Agents must never set it automatically."),
                  x_approved_by: Optional[str] = Header(None, description="Optional: name of the person who approved, written to the audit trail.")):
    """Approving executes the action (mock: a letter and a batch row are written to the outbox). Requires `X-Human-Approval: true`
    (`428 human_approval_required` otherwise). Four-eyes: a request cannot be approved by the key that asked for it (`409`)."""
    if (x_human_approval or "").strip().lower() != "true":
        C.audit(p.actor, p.role, "api_approval_without_human", action_id, {"decision": body.decision})
        raise APIError(428, "human_approval_required", "Send X-Human-Approval: true only after a person approved this action in your UI. Agents must not set it automatically.")
    a = C.q("SELECT status FROM actions WHERE action_id=?", [action_id])
    if not a:
        raise APIError(404, "not_found", "No such action.")
    if a[0]["status"] != "proposed":
        raise APIError(409, "not_pending", f"Action is already {a[0]['status']}.")
    if x_approved_by:
        C.audit(p.actor, p.role, "api_human_approval", action_id, {"decision": body.decision, "human": C.pseudonymise_query(x_approved_by[:80])})
    if E.decide_action(action_id, body.decision, p.actor, p.role) is False:
        raise APIError(409, "four_eyes_blocked", "The key that requested this action cannot approve it. Ask a colleague with a different key.")
    r = C.q("SELECT action_id, status, approved_by FROM actions WHERE action_id=?", [action_id])[0]
    return {"action_id": r["action_id"], "status": r["status"], "decided_by": r["approved_by"]}


@router.get("/audit", response_model=List[AuditRow], tags=["Audit"], summary="Audit trail (credit and compliance roles)", responses=ERRS)
def audit(object_id: Optional[str] = Query(None, description="e.g. CASE-0001 (also returns its actions A-CASE-0001-*)"),
          event: Optional[str] = Query(None, description="e.g. api_call, action_approved, access_denied"),
          limit: int = Query(200, ge=1, le=1000), p: Principal = Depends(credit_only)):
    """Real identifiers typed into questions are replaced by pseudonyms in the details."""
    rows = C.q("""SELECT * FROM audit WHERE (? IS NULL OR object_id = ? OR object_id LIKE ?) AND (? IS NULL OR event = ?)
                  ORDER BY ts DESC LIMIT ?""", [object_id, object_id, f"A-{object_id}-%", event, event, limit])
    out = []
    for r in rows:
        d = C.pseudonymise_query(r["detail"] or "{}")
        try: d = json.loads(d)
        except Exception: pass
        if p.team and isinstance(d, dict):
            d.pop("ip", None)              # arena teams don't see each other's addresses
        out.append(AuditRow(ts=str(r["ts"]), actor=r["actor"], role=r["role"], event=r["event"], object_id=r["object_id"], detail=d))
    return out


@router.get("/health", tags=["Public"], summary="Service health (public)")
def health():
    return {"status": "ok", "version": VERSION, "documents": C.q("SELECT count(*) n FROM documents")[0]["n"], "llm": llm.status(), "checker": checker_status()}


@router.get("/metrics", tags=["Public"], summary="Evaluation and red-team metrics (public, no personal data)")
def metrics():
    """Aggregated numbers only: test suites, red-team arena per round and category, model comparison, PII recall, autopilot."""
    return metrics_summary()


# ------------------------------------------------------------------ shared with the dashboard
def checker_status():
    if not os.environ.get("VERIFIER_URL"):
        return "not configured"
    return "down" if llm._down.get("verifier", 0) > time.time() else "configured"


def _j(path):
    try:
        return json.load(open(os.path.join(ROOT, path)))
    except Exception:
        return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def metrics_summary():
    out = {"product": "ALFRED: Agentic Ledger For Regulated Enterprise Decisions", "bank": "Lumen Bank (fictional, Turin)", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    suites = {}
    j = _j("runs/jury_checks.json")
    if isinstance(j, dict):
        suites["jury_checks"] = {"passed": j.get("passed"), "total": j.get("total"),
                                 "checks": [{"id": c.get("id"), "check": c.get("check"), "pass": bool(c.get("pass"))} for c in j.get("checks", []) if isinstance(c, dict)]}
    h = _j("runs/human_battery.json")
    if isinstance(h, dict):
        suites["human_battery"] = {k: h.get(k) for k in ("passed", "total", "pass_rate", "median_secs")}
    r = _j("runs/redteam_http.json")
    if isinstance(r, list):
        suites["redteam_http"] = {"passed": sum(1 for t in r if isinstance(t, dict) and t.get("pass")), "total": len(r)}
    a = _j("runs/api_checks.json")
    if isinstance(a, dict):
        suites["api_checks"] = {"passed": a.get("passed"), "total": a.get("total")}
    out["suites"] = suites
    rounds = []
    for i, d in enumerate(("runs/redteam", "runs/redteam_v2", "runs/redteam_v3"), 1):
        rep = _j(f"{d}/report.json")
        if not isinstance(rep, dict):
            if os.path.isdir(os.path.join(ROOT, d)):
                rounds.append({"round": i, "status": "running or incomplete"})
            continue
        tot = rep.get("totals") or {}
        cats = {k: {f: _num(v.get(f)) for f in ("n", "complied", "partial", "resisted", "attack_success_rate", "success_or_partial_rate")}
                for k, v in (rep.get("per_category") or {}).items() if isinstance(v, dict)}
        ben = rep.get("benign") or {}
        rounds.append({"round": i, "status": "complete", "generated": str(rep.get("generated", ""))[:10],
                       "prompts": _num(tot.get("prompts")), "attacks": _num(tot.get("attacks")), "benign": _num(tot.get("benign")),
                       "attack_success_rate": _num(rep.get("attack_success_rate")), "attack_success_or_partial_rate": _num(rep.get("attack_success_or_partial_rate")),
                       "real_data_leaks": _num(rep.get("real_data_leaks")), "unauthorised_actions": _num(rep.get("unauthorised_actions")),
                       "benign_false_refusal_rate": _num(ben.get("false_refusal_rate")), "per_category": cats})
    out["redteam_rounds"] = rounds
    m = _j("runs/metrics.json") or {}
    keys = ("triage.exact", "qa.ans_correct", "qa.ans_cited", "qa.unans_abstain", "qa.hallucinated", "extract_facts.key_recall", "latency_s", "n")
    out["models"] = {name: {k: _num((m.get(src) or {}).get(k)) for k in keys}
                     for name, src in (("base_qwen3.5_9b", "eval_student_base"), ("distilled_9b", "eval_student_distilled"), ("teacher_180b", "eval_teacher"))
                     if m.get(src)}
    pii = {}
    for ds, src in (("bank_heldout", m.get("pii_eval")), ("gretel_ood", m.get("pii_ood_eval"))):
        if isinstance(src, dict):
            pii[ds] = {k: _num(v.get("char_recall")) for k, v in src.items() if isinstance(v, dict) and "char_recall" in v}
    for f, tag in (("runs/pii_v2.json", ""), ("runs/pii_ensemble.json", "")):
        d = _j(f)
        if isinstance(d, dict):
            for ds, v in d.items():
                if isinstance(v, dict) and any(isinstance(x, dict) and "char_recall" in x for x in v.values()):
                    pii.setdefault(ds, {}).update({k: _num(x.get("char_recall")) for k, x in v.items() if isinstance(x, dict) and "char_recall" in x})
    out["pii_recall"] = pii
    ws = m.get("workspace_anon") or {}
    out["workspace_pii"] = {k: _num(ws.get(k)) for k in ("workspace_docs", "gold_pii_values", "leaked_values")}
    ap = m.get("autopilot") or {}
    out["autopilot_eval"] = {k: _num(ap.get(k)) for k in ("overdue_cases", "exceptions_stopped", "straight_through", "straight_through_pct", "manual_minutes_per_case", "est_minutes_saved_per_run")}
    try:
        ran = C.q("SELECT count(*) n FROM cases WHERE status <> 'new'")[0]["n"]
        if not ran:
            raise LookupError("autopilot not run yet")
        k = E.kpis()
        out["autopilot_live"] = {x: k.get(x) for x in ("cases", "straight_through", "exceptions", "pct_straight", "manual_minutes", "autopilot_minutes", "minutes_saved", "rule_accuracy", "model_accuracy", "exceptions_caught")}
    except Exception:
        out["autopilot_live"] = None
    try:
        s = C.q("""SELECT count(*) FILTER (WHERE event IN ('security_injection_attempt','access_denied','injection_flagged','security_memory_poisoning_blocked',
                   'four_eyes_blocked','proposal_refused','api_approval_without_human')) sec,
                   count(*) FILTER (WHERE event='security_injection_attempt') inj, count(*) FILTER (WHERE event='access_denied') den,
                   count(*) FILTER (WHERE event='four_eyes_blocked') fe, count(*) FILTER (WHERE event='api_call') api
                   FROM audit WHERE ts >= current_date""")[0]
        out["security_today"] = {"blocked_events": s["sec"], "prompt_injections": s["inj"], "access_denied": s["den"], "four_eyes_blocked": s["fe"], "api_calls": s["api"]}
    except Exception:
        out["security_today"] = None
    out["health"] = {"llm": llm.status(), "checker": checker_status()}
    # safety net: nothing that is a real vault value may leave through this public endpoint
    return json.loads(C.pseudonymise_query(json.dumps(out, ensure_ascii=False)))


# ------------------------------------------------------------------ wiring
def install(app):
    app.include_router(router)

    @app.exception_handler(APIError)
    async def _api_err(req, exc: APIError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status, headers=exc.headers)

    @app.middleware("http")
    async def _api_audit(request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        t0 = time.time()
        resp = await call_next(request)
        p = getattr(request.state, "principal", None)
        if p is not None:
            resp.headers["X-RateLimit-Limit"] = str(RATE)
            resp.headers["X-RateLimit-Remaining"] = str(getattr(request.state, "rate_left", 0))
        detail = {"method": request.method, "path": request.url.path, "status": resp.status_code, "ms": int((time.time() - t0) * 1000),
                  "key_id": p.key_id if p else None, "ip": request.client.host if request.client else None}
        if p is not None and p.team:
            detail["team"] = p.team
        try:
            await run_in_threadpool(C.audit, p.actor if p else "anonymous", p.role if p else "-", "api_call", request.url.path, detail)
        except Exception:
            pass
        return resp

    def _openapi():
        if not app.openapi_schema:
            app.openapi_schema = get_openapi(title=TITLE, version=VERSION, description=DESCRIPTION,
                                             routes=router.routes + [r for x in EXTRA_ROUTERS for r in x.routes],
                                             tags=[{"name": "Brain"}, {"name": "Privacy"}, {"name": "Memory"}, {"name": "Autopilot"},
                                                   {"name": "Approvals", "description": "Irreversible actions. Human approval required."},
                                                   {"name": "Audit"}, {"name": "Public", "description": "No key needed, no personal data."},
                                                   {"name": "Arena", "description": "Attack ALFRED: register a team, attack the API, file breach reports. Leaderboard at /arena."}])
        return app.openapi_schema
    app.openapi = _openapi
