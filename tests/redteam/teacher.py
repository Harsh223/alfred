"""Teacher / judge client (self-hosted, OpenAI-compatible vLLM endpoint). Never prints the token.

Config from env: TEACHER_URL, TEACHER_TOKEN (optional), RT_JUDGE_MODEL (default "teacher"),
LLM_AUTH_HEADER (optional header name; default is 'Authorization: Bearer <token>')."""
import os, json, time, urllib.request, functools


@functools.lru_cache(1)
def endpoint():
    url = os.environ.get('TEACHER_URL')
    if not url:
        raise RuntimeError('TEACHER_URL is not set')
    url = url.rstrip('/')
    return (url if url.endswith('/v1') else url + '/v1'), os.environ.get('TEACHER_TOKEN') or os.environ.get('LLM_TOKEN')


def _auth(tok):
    if not tok:
        return {}
    name = os.environ.get('LLM_AUTH_HEADER')
    return {name: tok} if name else {'Authorization': f'Bearer {tok}'}


def ready():
    try:
        url, tok = endpoint()
        r = urllib.request.urlopen(urllib.request.Request(url + '/models', headers=_auth(tok)), timeout=20)
        return r.status == 200
    except Exception:
        return False


def chat(messages, max_tokens=800, temperature=0.9, retries=3, timeout=180, json_mode=False):
    url, tok = endpoint()
    body = {"model": os.environ.get("RT_JUDGE_MODEL", "teacher"), "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for i in range(retries):
        try:
            req = urllib.request.Request(url + '/chat/completions', data=json.dumps(body).encode(),
                                         headers={'content-type': 'application/json', **_auth(tok)})
            d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            return d['choices'][0]['message']['content']
        except Exception:
            time.sleep(2 + 3 * i)
    return None
