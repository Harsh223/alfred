"""Branded API docs (/api/docs) in the comic / neo-brutalist theme of app/comic.py (light + dark).

Hero + quickstart cards + an endpoint index generated from the app's OpenAPI schema (grouped by tag), then an embedded
Swagger UI ("Try it") pointed at /api/openapi.json with theme overrides for both modes. The plain Swagger UI stays at /api/swagger.
"""
import html
from fastapi import Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app import comic as K

SWAGGER = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/"
BASE_URL = "https://alfred.harsh.one/v1"
ALIAS_HOST = "api.alfred.harsh.one"
CREDIT_ONLY = ("/v1/autopilot/", "/v1/actions", "/v1/audit")     # Depends(credit_only) in app/api.py
TAG_BLURB = {"Brain": "Ask questions and read the morning brief. Answers respect your key's role.",
             "Privacy": "Mask personal data before it goes anywhere else.",
             "Memory": "Facts people teach ALFRED. New facts stay pending until a different person approves.",
             "Autopilot": "Overdue-loan reminders: ALFRED prepares, a person approves.",
             "Approvals": "Irreversible actions. Human approval required.",
             "Audit": "Every call and decision, append-only.",
             "Public": "No key needed, no personal data.",
             "Arena": "Attack ALFRED: register a team, attack the API, file breach reports."}


def _e(x):
    return html.escape(str(x))


def _badges(path, method, op):
    hdrs = {p.get("name", "").lower() for p in op.get("parameters", []) if p.get("in") == "header"}
    out = []
    if "x-admin-token" in hdrs:
        out.append(K.chip("organisers", "red"))
    elif path == "/v1/arena/breach":
        out.append(K.chip("arena team key", "blue"))
    elif op.get("security"):
        out.append(K.chip("api key"))
        if path.startswith(CREDIT_ONLY):
            out.append(K.chip("credit + compliance", "blue"))
    else:
        out.append(K.chip("public", "ylw"))
    if "x-human-approval" in hdrs:
        out.append(K.chip("human approval", "red"))
    return "".join(out)


def endpoint_index(schema):
    tags = [t["name"] for t in schema.get("tags", [])]
    groups = {}
    for path, ops in schema.get("paths", {}).items():
        for m, op in ops.items():
            if m not in ("get", "post", "put", "patch", "delete"):
                continue
            tg = (op.get("tags") or ["Other"])[0]
            groups.setdefault(tg, []).append((path, m, op))
            if tg not in tags:
                tags.append(tg)
    cards = []
    for tg in tags:
        rows = groups.get(tg)
        if not rows:
            continue
        li = "".join(
            f'<a class="d-ep" href="#/{_e(tg)}/{_e(op.get("operationId", ""))}" data-op="{_e(tg)}/{_e(op.get("operationId", ""))}">{K.method(m)}'
            f'<span class="d-ep-t"><code class="d-path">{_e(path)}</code><span class="d-sum">{_e(op.get("summary", ""))}</span></span>'
            f'<span class="d-bd">{_badges(path, m, op)}</span></a>' for path, m, op in rows)
        cards.append(K.card(f'<div class="k-card-h"><h3 class="k-h3">{_e(tg)}</h3>{K.chip(f"{len(rows)} endpoint" + ("s" if len(rows) != 1 else ""))}</div>'
                            f'<p class="d-blurb">{_e(TAG_BLURB.get(tg, ""))}</p><div class="d-eps">{li}</div>', "d-group"))
    return "".join(cards)


DCSS = """
.d-hero .k-h1{font-size:clamp(32px,4.6vw,56px)}
.d-quick{grid-template-columns:repeat(2,minmax(0,1fr))}.d-quick .d-wide{grid-column:1/-1}
@media (max-width:820px){.d-quick{grid-template-columns:minmax(0,1fr)}}
.d-urls{display:flex;flex-wrap:wrap;gap:12px;margin-top:22px}
.d-url{display:inline-flex;align-items:center;gap:10px;border:2.5px solid var(--k-line);border-radius:12px;background:var(--k-card);padding:8px 12px;box-shadow:3px 3px 0 var(--k-shadow);min-width:0;max-width:100%}
.d-url span{font:800 10.5px/1 var(--k-body);letter-spacing:.1em;text-transform:uppercase;color:var(--k-mute)}
.d-url code{font:600 14px var(--k-mono);color:var(--k-ink);word-break:break-all}
.d-q{display:flex;flex-direction:column}
.d-q p{margin:6px 0 0;color:var(--k-ink2);font-size:14.5px}
.d-q .a-step{display:flex;gap:12px;align-items:center;margin-bottom:4px}
.d-q .k-badge{width:40px;height:40px;font-size:18px}
.d-q ul{margin:10px 0 0;padding-left:18px;color:var(--k-ink2);font-size:14px}.d-q li{margin:5px 0}
.d-q.k-hl p,.d-q.k-hl ul{color:#2b2610}
.d-groups{columns:2 480px;column-gap:22px}.d-groups>.k-card{break-inside:avoid;margin:0 0 22px;display:block}
.d-blurb{margin:-6px 0 12px;color:var(--k-mute);font-size:13.5px}
.d-eps{display:grid;gap:8px}
.d-ep{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 10px;border:2px solid transparent;border-radius:10px;
  text-decoration:none;color:var(--k-ink);font-weight:500;transition:background .08s,border-color .08s}
.d-ep:hover,.d-ep:focus-visible{background:var(--k-tint);border-color:var(--k-line);outline:none}
.d-ep-t{display:flex;flex-direction:column;min-width:0;gap:2px}
.d-path{font:600 13.5px var(--k-mono);color:var(--k-ink);word-break:break-all}
.d-sum{font-size:13px;color:var(--k-ink2)}
.d-bd{display:flex;flex-wrap:wrap;gap:5px;justify-content:flex-end;max-width:190px}
@media (max-width:560px){.d-ep{grid-template-columns:auto minmax(0,1fr)}.d-bd{grid-column:2;justify-content:flex-start;max-width:none}}
.d-try{padding:8px 8px 18px}

/* ---------- Swagger UI, themed (light + dark) ---------- */
.swagger-ui{font-family:var(--k-body);color:var(--k-ink)}
.swagger-ui .wrapper{padding:0 14px;max-width:none}
.swagger-ui .information-container,.swagger-ui .info{display:none}
.swagger-ui .scheme-container{background:transparent;box-shadow:none;padding:16px 0 4px;margin:0}
.swagger-ui .scheme-container .schemes{align-items:center}
.swagger-ui .opblock-tag-section{margin-bottom:6px}
.swagger-ui .opblock-tag{font:22px/1.2 var(--k-display);color:var(--k-ink);border-bottom:2.5px solid var(--k-line);padding:14px 4px 10px;margin:0 0 8px}
.swagger-ui .opblock-tag small{font:500 13.5px var(--k-body);color:var(--k-ink2);padding-left:12px}
.swagger-ui .opblock-tag svg,.swagger-ui .opblock-tag button svg{fill:var(--k-ink)}
.swagger-ui .opblock{border:2.5px solid var(--k-line)!important;border-radius:12px;box-shadow:4px 4px 0 var(--k-shadow);margin:0 0 14px;background:var(--k-card)!important;overflow:hidden}
.swagger-ui .opblock .opblock-summary{border-bottom:0;padding:8px 10px}
.swagger-ui .opblock.is-open .opblock-summary{border-bottom:2.5px solid var(--k-line)}
.swagger-ui .opblock .opblock-summary-method{font:800 12px/1 var(--k-body);letter-spacing:.08em;border:2px solid #111;border-radius:6px;box-shadow:2px 2px 0 #111;padding:7px 0;min-width:72px;text-shadow:none}
.swagger-ui .opblock.opblock-get .opblock-summary-method{background:#2f5bd3;color:#fff}
.swagger-ui .opblock.opblock-post .opblock-summary-method{background:#f5c542;color:#111}
.swagger-ui .opblock.opblock-delete .opblock-summary-method{background:#d9483b;color:#fff}
.swagger-ui .opblock.opblock-put .opblock-summary-method,.swagger-ui .opblock.opblock-patch .opblock-summary-method{background:#ee6a55;color:#111}
.swagger-ui .opblock.opblock-get{--d-m:rgba(47,91,211,.10)}.swagger-ui .opblock.opblock-post{--d-m:rgba(245,197,66,.20)}.swagger-ui .opblock.opblock-delete{--d-m:rgba(217,72,59,.12)}
.swagger-ui .opblock .opblock-summary{background:var(--d-m,transparent)}
:root[data-theme=dark] .swagger-ui .opblock .opblock-summary{background:transparent}
.swagger-ui .opblock-summary-control{background:transparent!important}
.swagger-ui .opblock-summary .view-line-link,.swagger-ui .opblock-summary .copy-to-clipboard{display:none}
.swagger-ui .opblock .opblock-summary-path,.swagger-ui .opblock .opblock-summary-path__deprecated{font:600 14.5px var(--k-mono);color:var(--k-ink)}
.swagger-ui .opblock .opblock-summary-description{font-size:13.5px;color:var(--k-ink2);font-weight:500}
.swagger-ui .opblock .opblock-section-header{background:var(--k-card2);box-shadow:none;border-bottom:2px dashed var(--k-grid)}
.swagger-ui .opblock .opblock-section-header h4,.swagger-ui .opblock-description-wrapper p,.swagger-ui .opblock-external-docs-wrapper p,
.swagger-ui .opblock-title_normal p,.swagger-ui .response-col_status,.swagger-ui .response-col_links,.swagger-ui table thead tr td,.swagger-ui table thead tr th,
.swagger-ui .parameter__name,.swagger-ui .parameter__type,.swagger-ui .parameter__in,.swagger-ui .parameter__extension,.swagger-ui .parameter__deprecated,
.swagger-ui .tab li,.swagger-ui .tab li button.tablinks,.swagger-ui .responses-inner h4,.swagger-ui .responses-inner h5,.swagger-ui label,.swagger-ui .btn,
.swagger-ui .markdown p,.swagger-ui .markdown li,.swagger-ui .renderedMarkdown p,.swagger-ui .renderedMarkdown li,.swagger-ui .model-title,.swagger-ui .model,
.swagger-ui section.models h4,.swagger-ui .servers-title,.swagger-ui .servers>label,.swagger-ui .response-control-media-type__title,.swagger-ui .opblock-summary-operation-id,
.swagger-ui .dialog-ux .modal-ux-header h3,.swagger-ui .dialog-ux .modal-ux-content p,.swagger-ui .dialog-ux .modal-ux-content h4,.swagger-ui .auth-container h4,
.swagger-ui .auth-container h6,.swagger-ui .scopes h2,.swagger-ui .loading-container .loading:after,.swagger-ui .request-url,.swagger-ui .prop-format,
.swagger-ui .parameters-col_description,.swagger-ui .response-col_description,.swagger-ui .col_header,.swagger-ui .opblock-summary-control,.swagger-ui .model-toggle:after,
.swagger-ui table.model tr.property-row td,.swagger-ui .json-schema-2020-12__title,.swagger-ui .json-schema-2020-12-keyword__name,.swagger-ui .json-schema-2020-12-keyword__value{color:var(--k-ink)}
.swagger-ui .parameter__name.required:after,.swagger-ui .parameter__name.required span{color:var(--k-bad)}
.swagger-ui .prop-type{color:var(--k-blue)}:root[data-theme=dark] .swagger-ui .prop-type{color:#9db7ff}
.swagger-ui .parameter__in,.swagger-ui .parameter__type{font-family:var(--k-mono);color:var(--k-mute)}
.swagger-ui table thead tr td,.swagger-ui table thead tr th{border-bottom:2.5px solid var(--k-line);font:800 11px var(--k-body);letter-spacing:.08em;text-transform:uppercase}
.swagger-ui .responses-inner h4,.swagger-ui .responses-inner h5{font-weight:800}
.swagger-ui .tab li:first-of-type:after{background:var(--k-grid)}
.swagger-ui .markdown code,.swagger-ui .renderedMarkdown code{font:600 12.5px var(--k-mono);background:var(--k-tint);color:var(--k-ink);border-radius:4px;padding:1px 5px}
.swagger-ui .btn{font:800 12px/1 var(--k-body);letter-spacing:.05em;text-transform:uppercase;border:2.5px solid var(--k-line);border-radius:999px;padding:9px 16px;
  background:var(--k-card);box-shadow:3px 3px 0 var(--k-shadow);color:var(--k-ink)}
.swagger-ui .btn:hover{box-shadow:4px 4px 0 var(--k-shadow)}
.swagger-ui .btn.execute{background:#d9483b;color:#fff;border-color:var(--k-line)}
.swagger-ui .btn.authorize{background:#f5c542;color:#111;border-color:var(--k-line)}.swagger-ui .btn.authorize svg{fill:#111}
.swagger-ui .btn.cancel{background:var(--k-card);color:var(--k-bad);border-color:var(--k-bad)}
.swagger-ui .btn-group .btn{border-radius:999px}
.swagger-ui .try-out__btn{background:var(--k-card)}
.swagger-ui .authorization__btn svg,.swagger-ui .opblock-control-arrow svg,.swagger-ui .expand-operation svg,.swagger-ui .opblock-summary-control svg{fill:var(--k-ink)}
.swagger-ui input[type=text],.swagger-ui input[type=password],.swagger-ui input[type=search],.swagger-ui input[type=email],.swagger-ui input[type=file],.swagger-ui textarea,.swagger-ui select{
  font:14px var(--k-body);background:var(--k-card2);color:var(--k-ink);border:2.5px solid var(--k-line);border-radius:10px;box-shadow:none}
.swagger-ui textarea{font-family:var(--k-mono);font-size:13px}
.swagger-ui select{background-image:none;padding-right:10px}
.swagger-ui .parameters-col_description input,.swagger-ui .body-param__text{background:var(--k-card2)!important;color:var(--k-ink)!important}
.swagger-ui .highlight-code,.swagger-ui .microlight,.swagger-ui pre.microlight,.swagger-ui .opblock-body pre.microlight{background:#15142f!important;color:#f3efe3!important;
  font:12.5px/1.6 var(--k-mono)!important;border:2.5px solid var(--k-line);border-radius:10px}
:root[data-theme=dark] .swagger-ui .opblock-body pre.microlight,:root[data-theme=dark] .swagger-ui .highlight-code .microlight{background:#0b0a24!important}
.swagger-ui .microlight span{color:inherit}
.swagger-ui .copy-to-clipboard{background:#f5c542;border:2px solid #111;border-radius:8px;bottom:8px;right:10px}
.swagger-ui .copy-to-clipboard button{background:url("data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='15' aria-hidden='true'><g transform='translate(2 -1)'><path fill='%23111' fill-rule='evenodd' d='M2 13h4v1H2v-1zm5-6H2v1h5V7zm2 3V8l-3 3 3 3v-2h5v-2H9zM4.5 9H2v1h2.5V9zM2 12h2.5v-1H2v1zm9 1h1v2c-.02.28-.11.52-.3.7-.19.18-.42.28-.7.3H1c-.55 0-1-.45-1-1V4c0-.55.45-1 1-1h3c0-1.11.89-2 2-2 1.11 0 2 .89 2 2h3c.55 0 1 .45 1 1v5h-1V6H1v9h10v-2zM2 5h8c0-.55-.45-1-1-1H8c-.55 0-1-.45-1-1s-.45-1-1-1-1 .45-1 1-.45 1-1 1H3c-.55 0-1 .45-1 1z'/></g></svg>") 50% no-repeat}
.swagger-ui .model-box{background:var(--k-card2);border:2px solid var(--k-grid);border-radius:10px}
.swagger-ui section.models{border:2.5px solid var(--k-line);border-radius:12px;box-shadow:4px 4px 0 var(--k-shadow);background:var(--k-card)}
.swagger-ui section.models.is-open h4{border-bottom:2px dashed var(--k-grid)}
.swagger-ui section.models .model-container{background:var(--k-card2);border-radius:8px}
.swagger-ui section.models .model-container:hover{background:var(--k-tint)}
.swagger-ui section.models h4 svg{fill:var(--k-ink)}
.swagger-ui .model .property.primitive,.swagger-ui .model span{color:var(--k-ink2)}
.swagger-ui .model-hint{background:#111;color:#fff}
.swagger-ui .response-control-media-type--accept-controller select{border-color:var(--k-ok)}
.swagger-ui .responses-table .response,.swagger-ui table tbody tr td{border-color:var(--k-grid)}
.swagger-ui .dialog-ux .backdrop-ux{background:rgba(10,10,30,.6)}
.swagger-ui .dialog-ux .modal-ux{background:var(--k-card);border:3px solid var(--k-line);border-radius:16px;box-shadow:6px 6px 0 var(--k-shadow)}
.swagger-ui .dialog-ux .modal-ux-header{border-bottom:2.5px solid var(--k-line)}
.swagger-ui .dialog-ux .modal-ux-header .close-modal svg{fill:var(--k-ink)}
.swagger-ui .auth-container{border-bottom:2px dashed var(--k-grid)}
.swagger-ui .auth-container .wrapper{padding:0}
.swagger-ui a.nostyle,.swagger-ui a.nostyle:visited{color:var(--k-ink)}
.swagger-ui a{color:var(--k-link)}
.swagger-ui .opblock-body .opblock-loading-animation{border-color:var(--k-grid);border-top-color:var(--k-red)}
.swagger-ui .response-col_status .response-undocumented{color:var(--k-mute)}
.swagger-ui .opblock .opblock-section-header>label>span{color:var(--k-ink)}
.swagger-ui .opblock.is-open.d-flash{animation:d-flash 1.2s ease-out}
@keyframes d-flash{0%{box-shadow:0 0 0 6px var(--k-yellow),4px 4px 0 var(--k-shadow)}100%{box-shadow:4px 4px 0 var(--k-shadow)}}
.swagger-ui .opblock-summary-path__deprecated{text-decoration:line-through}
:root[data-theme=dark] .swagger-ui :is(.opblock-body,.opblock-description-wrapper,.dialog-ux,section.models) :is(p,small,div,td,th,label,h4,h5,i){color:var(--k-ink)}
:root[data-theme=dark] .swagger-ui .opblock-body :is(.opblock-section-header h4,.response-control-media-type__accept-message){color:var(--k-ink2)}
.swagger-ui .errors-wrapper{background:var(--k-tint);border:2px solid var(--k-bad);color:var(--k-ink)}
.swagger-ui .errors-wrapper hgroup h4,.swagger-ui .errors-wrapper .errors small{color:var(--k-ink)}
:root[data-theme=dark] .swagger-ui .json-schema-2020-12-accordion__icon svg,:root[data-theme=dark] .swagger-ui .json-schema-2020-12-expand-deep-button{fill:var(--k-ink);color:var(--k-ink)}
@media (max-width:560px){.swagger-ui .opblock .opblock-summary{flex-wrap:wrap}.swagger-ui .opblock .opblock-summary-description{flex-basis:100%;padding-top:4px}
  .swagger-ui .opblock .opblock-summary-path{max-width:calc(100% - 110px)}.swagger-ui .wrapper{padding:0 6px}}
"""


def render(schema):
    info = schema.get("info", {})
    nep = sum(1 for ops in schema.get("paths", {}).values() for m in ops if m in ("get", "post", "put", "patch", "delete"))
    steps = (("1", "One key, one role", "The key decides what you may see"), ("2", "Pseudonyms only", "The API never re-identifies"),
             ("3", "Humans approve", "Irreversible steps need a person"))
    st = "".join(f'<div class="k-step">{K.badge(n)}<div><b>{_e(t)}</b><small>{_e(d)}</small></div></div>' for n, t, d in steps)
    c_reg = f"curl -s -X POST {BASE_URL}/arena/register \\\n  -H 'Content-Type: application/json' \\\n  -d '{{\"team\":\"Your Team\"}}'"
    c_ask = (f"curl -s {BASE_URL}/ask \\\n  -H \"X-API-Key: $KEY\" \\\n  -H 'Content-Type: application/json' \\\n"
             f"  -d '{{\"question\":\"Which company is breaching its covenant?\"}}'")
    c_appr = (f"# only after a person approved it in YOUR UI\ncurl -s -X POST {BASE_URL}/actions/$ID/decision \\\n  -H \"X-API-Key: $KEY\" \\\n"
              f"  -H 'X-Human-Approval: true' \\\n  -H 'Content-Type: application/json' \\\n  -d '{{\"decision\":\"approved\"}}'")
    c_err = '{\n  "error": {\n    "code": "forbidden_for_role",\n    "message": "Not available for your role."\n  }\n}'
    q = lambda n, title, inner, cls="": K.card(f'<div class="a-step">{K.badge(n)}<h3 class="k-h3">{_e(title)}</h3></div>{inner}', "d-q " + cls)
    quick = (q(1, "Register a team key", '<p>Public, no key needed. You get a <b>Finance</b> (<code class=k-ic>rm_credit</code>) and a <b>Tech</b> '
               '(<code class=k-ic>it_support</code>) key, shown once.</p>' + K.code(c_reg, "q-reg", "curl · register"))
             + q(2, "Ask a question", '<p>Send <code class=k-ic>X-API-Key</code>. A role in the body or in the question is ignored: the key decides.</p>'
                 + K.code(c_ask, "q-ask", "curl · ask"))
             + q(3, "The X-Human-Approval rule", '<p>Approving an action executes it. Send <code class=k-ic>X-Human-Approval: true</code> <b>only after a person '
                 'approved it</b>. Agents must never set it. Missing header → <code class=k-ic>428</code>. Whoever proposed it cannot approve it (four-eyes, '
                 '<code class=k-ic>409</code>).</p>' + K.code(c_appr, "q-appr", "curl · approve"), "k-hl d-wide")
             + q(4, "Rate limits", '<ul><li><b>60 requests per minute</b> per key.</li><li>Beyond that: <code class=k-ic>429</code> with <code class=k-ic>Retry-After</code>.</li>'
                 '<li>Every response carries <code class=k-ic>X-RateLimit-Limit</code> and <code class=k-ic>X-RateLimit-Remaining</code>.</li>'
                 '<li>Every call is written to the audit trail.</li></ul>')
             + q(5, "Error shape", '<p>Always the same JSON body:</p>' + K.code(c_err, "q-err", "json")
                 + '<p class="k-small"><b>401</b> bad key · <b>403</b> role · <b>404</b> · <b>409</b> four-eyes / not pending · <b>422</b> invalid or blocked · '
                   '<b>428</b> no human approval · <b>429</b> rate limit</p>'))
    body = f"""{K.topbar([("OpenAPI JSON", "/api/openapi.json"), ("Plain Swagger", "/api/swagger"), ("Metrics", "/dashboard"), ("Attack ALFRED", "/arena", True)], logo_href="/dashboard")}
<main class="k-wrap">
<section class="k-hero d-hero"><div class="k-hero-grid"><div>
{K.tag("ALFRED API")}
{K.h1("Build on the AI that never acts without asking")}
<p class="k-lede">REST + JSON for the Company Brain and the overdue-loan Autopilot of <b>Lumen Bank</b> (fictional, synthetic data).
{nep} endpoints · OpenAPI {_e(schema.get("openapi", "3"))} · v{_e(info.get("version", "1"))}.</p>
<div class="d-urls"><div class="d-url"><span>Base URL</span><code>{BASE_URL}</code></div><div class="d-url"><span>Also</span><code>{ALIAS_HOST}</code></div></div>
<div class="k-steps">{st}</div></div>
<div class="k-art"><div class="k-bubble">X-Human-Approval? Only after a person says yes.</div>{K.mascot("Alfred the butler-owl holding a shield")}</div></div></section>

{K.section_head("QUICKSTART", "Five things to know", "Everything below also works against this server: swap the base URL.")}
<div class="k-grid d-quick">{quick}</div>

{K.section_head("ENDPOINTS", "Endpoint index", "Generated from <a href='/api/openapi.json'>/api/openapi.json</a>. Click one to open it in Try it below.")}
<div class="d-groups">{endpoint_index(schema)}</div>

<div id="try">{K.section_head("TRY IT", "Call the live API", "Click <b>Authorize</b>, paste your <code class=k-ic>X-API-Key</code>, open an endpoint, <b>Try it out</b>, <b>Execute</b>. Requests go to this server.")}</div>
{K.card('<div id="swagger-ui"><p class="k-muted" style="padding:14px">Loading Swagger UI…</p></div>', "d-try")}

<div class="k-foot">Synthetic data only: Lumen Bank and every person in it are fictional. <a href="/api/openapi.json">OpenAPI JSON</a> ·
<a href="/api/swagger">Plain Swagger UI</a> · <a href="/arena">Attack ALFRED</a> · <a href="/dashboard">Metrics dashboard</a></div>
</main>"""
    head = f'<link rel="stylesheet" href="{SWAGGER}swagger-ui.css">'
    js = f"""<script src="{SWAGGER}swagger-ui-bundle.js" crossorigin></script><script>
(function(){{function go(){{if(!window.SwaggerUIBundle){{document.getElementById('swagger-ui').innerHTML='<p class="k-muted" style="padding:14px">Swagger UI could not load. Use <a href="/api/openapi.json">/api/openapi.json</a>.</p>';return}}
window.ui=SwaggerUIBundle({{url:'/api/openapi.json',dom_id:'#swagger-ui',deepLinking:true,docExpansion:'list',defaultModelsExpandDepth:0,
persistAuthorization:true,displayRequestDuration:true,tryItOutEnabled:false,filter:false,syntaxHighlight:{{activated:true,theme:'monokai'}}}});
document.querySelectorAll('.d-ep').forEach(function(a){{a.addEventListener('click',function(){{var id=a.getAttribute('data-op');
setTimeout(function(){{var el=document.getElementById('operations-'+id.replace('/','-'));if(el){{if(!el.classList.contains('is-open')){{var s=el.querySelector('.opblock-summary-control');if(s)s.click()}}
el.scrollIntoView({{behavior:'smooth',block:'start'}});el.classList.add('d-flash');setTimeout(function(){{el.classList.remove('d-flash')}},1300)}}
else document.getElementById('try').scrollIntoView({{behavior:'smooth'}})}},60)}})}})}}
if(document.readyState!=='loading')go();else document.addEventListener('DOMContentLoaded',go)}})();</script>"""
    return K.page("ALFRED API docs", body + K.COPY_JS + js, extra_css=DCSS, head=head)


def install(app):
    @app.get("/api/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_docs():
        """Branded API docs: quickstart, endpoint index from the OpenAPI schema, embedded Swagger UI (light + dark)."""
        return HTMLResponse(render(app.openapi()))

    @app.get("/api/swagger", response_class=HTMLResponse, include_in_schema=False)
    def api_swagger():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="ALFRED API · Swagger UI",
                                   swagger_js_url=SWAGGER + "swagger-ui-bundle.js", swagger_css_url=SWAGGER + "swagger-ui.css")
