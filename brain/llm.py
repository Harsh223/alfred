"""OpenAI-compatible client with a fallback chain: student -> teacher -> offline stub (returns None)."""
import os, re, time, threading
from openai import OpenAI

_down = {}            # name -> retry-after timestamp
_lock = threading.Lock()


def _endpoints():
    out = []
    for name, env in (("student", "STUDENT_URL"), ("teacher", "TEACHER_URL")):
        url = os.environ.get(env)
        if url:
            out.append((name, url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1") else "/v1")))
    return out


def auth_headers(tok):
    """Auth header for a self-hosted endpoint. Default: 'Authorization: Bearer <token>'.
    If LLM_AUTH_HEADER is set, the token is sent raw under that header name instead."""
    if not tok:
        return {}
    name = os.environ.get("LLM_AUTH_HEADER")
    return {name: tok} if name else {"Authorization": f"Bearer {tok}"}


def _client(url):
    # per-endpoint tokens (STUDENT_TOKEN / TEACHER_TOKEN), falling back to a shared LLM_TOKEN
    tok = None
    for name, env in (("student", "STUDENT_URL"), ("teacher", "TEACHER_URL")):
        if os.environ.get(env) and url.startswith(os.environ[env].rstrip("/").removesuffix("/v1")):
            tok = os.environ.get(f"{name.upper()}_TOKEN")
    tok = tok or os.environ.get("LLM_TOKEN")
    headers = auth_headers(tok)
    return OpenAI(base_url=url, api_key=os.environ.get("LLM_API_KEY", "local"), default_headers=headers,
                  timeout=float(os.environ.get("LLM_TIMEOUT", "40")), max_retries=0)


def strip_think(t):
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S)
    return t.split("</think>")[-1].strip()


def chat(messages, max_tokens=600, temperature=0.0):
    """Returns (text, model_name) or (None, 'stub') if every endpoint is unavailable."""
    for name, url in _endpoints():
        with _lock:
            if _down.get(name, 0) > time.time():
                continue
        try:
            t0 = time.time()
            r = _client(url).chat.completions.create(
                model=name, messages=messages, max_tokens=max_tokens, temperature=temperature,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            txt = strip_think(r.choices[0].message.content)
            if txt:
                return txt, f"{name} ({time.time() - t0:.1f}s)"
        except Exception:
            with _lock:
                _down[name] = time.time() + 60
    return None, "stub"


def status():
    s = {}
    for name, url in _endpoints():
        s[name] = "down" if _down.get(name, 0) > time.time() else "configured"
    return s


# ------------------------------------------------------------------ independent answer checker (different model: Qwen3.8-27B)
VERIFY_PROMPT = ("You are an independent checker at a bank. Decide whether EVERY factual claim in the ANSWER (numbers, dates, names, IDs, rules) "
                 "is directly supported by the SOURCES, AND whether it answers the QUESTION exactly as asked. Paraphrase is fine; anything added, changed or not in the sources is UNSUPPORTED. "
                 "If the question asks about a different year, place, product, person or version than the sources cover (e.g. '2019', 'Spain', 'weekly batch'), "
                 "or the answer talks about something else than what was asked, it is UNSUPPORTED.\n\n"
                 "SOURCES:\n{src}\n\nQUESTION: {q}\nANSWER: {a}\n\nReply with exactly one word: SUPPORTED or UNSUPPORTED.")


def verify(question, answer, sources):
    """Returns (verdict, model): verdict in {'supported','unsupported', None (checker unavailable)}."""
    url = os.environ.get("VERIFIER_URL")
    if not url or _down.get("verifier", 0) > time.time():
        return None, "no checker"
    try:
        headers = auth_headers(os.environ.get("VERIFIER_TOKEN"))
        cli = OpenAI(base_url=url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1") else "/v1"), api_key="local", default_headers=headers,
                     timeout=float(os.environ.get("VERIFY_TIMEOUT", "20")), max_retries=0)
        t0 = time.time()
        r = cli.chat.completions.create(model="verifier", messages=[{"role": "user", "content": VERIFY_PROMPT.format(
            src="\n".join(f"[{s['doc_id']}] {s['text']}" for s in sources), q=question, a=answer)}], max_tokens=5, temperature=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        out = strip_think(r.choices[0].message.content).upper()
        return ("unsupported" if "UNSUPPORTED" in out else "supported" if "SUPPORTED" in out else None), f"checker Qwen3.8-27B ({time.time() - t0:.1f}s)"
    except Exception:
        _down["verifier"] = time.time() + 60
        return None, "no checker"


# ------------------------------------------------------------------ live health probe (for the dashboard "warming up" state)
_health_cache = {"t": 0, "v": None}


def _probe(url, tok):
    import urllib.request
    try:
        req = urllib.request.Request(url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1") else "/v1") + "/models", headers=auth_headers(tok))
        return urllib.request.urlopen(req, timeout=4).status == 200
    except Exception:
        return False


def health():
    """{'assistant': 'up'|'loading'|'off', 'checker': ..., 'ready': bool} — probed live, cached 15 s.
    'loading' = configured but not answering (e.g. the model server is restarting after a hardware swap)."""
    if time.time() - _health_cache["t"] < 15 and _health_cache["v"]:
        return _health_cache["v"]
    out = {}
    for key, uenv, tenv in (("assistant", "STUDENT_URL", "STUDENT_TOKEN"), ("checker", "VERIFIER_URL", "VERIFIER_TOKEN")):
        url = os.environ.get(uenv)
        out[key] = "off" if not url else ("up" if _probe(url, os.environ.get(tenv) or os.environ.get("LLM_TOKEN")) else "loading")
    out["ready"] = out["assistant"] == "up" and out["checker"] in ("up", "off")
    _health_cache.update(t=time.time(), v=out)
    return out
