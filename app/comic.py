"""Comic / manga hackathon theme for public pages (/dashboard, later /arena).

Bold neo-brutalist look: thick outlines, hard offset shadows, chunky display type, yellow tag labels,
speed lines (dark) / halftone dots (light). Light + dark via `:root[data-theme=light|dark]`, defaulting to
prefers-color-scheme; a toggle persists the choice in localStorage (and in the URL hash as a fallback, so a
timed reload keeps it). Pure CSS + a few lines of inline JS, no external scripts.

Usage:
    from app import comic as K
    html = K.page("Title", K.topbar(links=[("JSON", "/v1/metrics")]) + "<main class='k-wrap'>...</main>", refresh=30)

Building blocks (all return HTML strings): tag, h1, h2, section_head, badge, chip, card, stat, button,
toggle_button, mascot, topbar. Classes are prefixed `k-` so they never collide with app/ui.py styles.
"""
import html as _html
import math

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Bowlby+One&family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">')

# --------------------------------------------------------------------------- tokens
TOKENS = """
:root{--k-display:"Bowlby One","Arial Black","Helvetica Neue",Impact,sans-serif;
--k-mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--k-body:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
--k-red:#d9483b;--k-coral:#ee6a55;--k-yellow:#f5c542;--k-blue:#2f5bd3;--k-black:#111111;--k-white:#ffffff;
--k-r:14px;--k-bw:3px;--k-off:6px}
:root,:root[data-theme=light]{color-scheme:light;
--k-bg:#fdf5e4;--k-bg2:#f7e9cc;--k-ink:#141414;--k-ink2:#36332d;--k-mute:#5c574d;--k-card:#ffffff;--k-card2:#fffaf0;
--k-line:#141414;--k-shadow:#141414;--k-grid:rgba(20,20,20,.14);--k-dot:rgba(20,20,20,.16);--k-ray:transparent;
--k-head-shadow:#d9483b;--k-tag-bg:#141414;--k-tag-ink:#f5c542;--k-chip-bg:#141414;--k-chip-ink:#ffffff;
--k-tint:rgba(245,197,66,.32);--k-ok:#16794a;--k-bad:#c0322a;--k-warn:#9a5b00;--k-link:#1d47b8}
:root[data-theme=dark]{color-scheme:dark;
--k-bg:#1b1a4d;--k-bg2:#23226a;--k-ink:#fbf7ee;--k-ink2:#dcdaf3;--k-mute:#b3b1dc;--k-card:#13123a;--k-card2:#1a1950;
--k-line:#f3efe3;--k-shadow:#07061c;--k-grid:rgba(243,239,227,.16);--k-dot:rgba(255,255,255,.07);--k-ray:rgba(120,118,230,.13);
--k-head-shadow:#d9483b;--k-tag-bg:#f5c542;--k-tag-ink:#111111;--k-chip-bg:#f3efe3;--k-chip-ink:#111111;
--k-tint:rgba(245,197,66,.16);--k-ok:#5fd394;--k-bad:#ff8a7a;--k-warn:#ffc46b;--k-link:#ffd76a}
@media (prefers-color-scheme:dark){:root:not([data-theme]){color-scheme:dark;
--k-bg:#1b1a4d;--k-bg2:#23226a;--k-ink:#fbf7ee;--k-ink2:#dcdaf3;--k-mute:#b3b1dc;--k-card:#13123a;--k-card2:#1a1950;
--k-line:#f3efe3;--k-shadow:#07061c;--k-grid:rgba(243,239,227,.16);--k-dot:rgba(255,255,255,.07);--k-ray:rgba(120,118,230,.13);
--k-tag-bg:#f5c542;--k-tag-ink:#111111;--k-chip-bg:#f3efe3;--k-chip-ink:#111111;
--k-tint:rgba(245,197,66,.16);--k-ok:#5fd394;--k-bad:#ff8a7a;--k-warn:#ffc46b;--k-link:#ffd76a}}
"""

# --------------------------------------------------------------------------- components
COMPONENTS = """
*{box-sizing:border-box}
html{background:var(--k-bg)}
body{margin:0;background:var(--k-bg);color:var(--k-ink);font:15px/1.55 var(--k-body);-webkit-font-smoothing:antialiased;overflow-x:hidden;position:relative}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(circle,var(--k-dot) 1.7px,transparent 2px) 0 0/16px 16px;
  -webkit-mask-image:radial-gradient(ellipse at 0% 100%,#000 0,transparent 55%);mask-image:radial-gradient(ellipse at 0% 100%,#000 0,transparent 55%)}
body>*{position:relative;z-index:1}
a{color:var(--k-link);font-weight:600;text-underline-offset:3px}
h1,h2,h3{margin:0}
.k-wrap{max-width:1180px;margin:0 auto;padding:0 16px}
.k-muted{color:var(--k-mute)}.k-small{font-size:13px}

/* top bar */
.k-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 0}
.k-logo{font:26px/1 var(--k-display);letter-spacing:.5px;color:var(--k-ink);text-shadow:2px 2px 0 var(--k-head-shadow);text-decoration:none}
.k-top .k-sp{flex:1}
.k-nav{display:flex;gap:10px;flex-wrap:wrap;align-items:center}

/* buttons + toggle */
.k-btn{display:inline-flex;align-items:center;gap:7px;font:800 13px/1 var(--k-body);text-transform:uppercase;letter-spacing:.04em;
  color:var(--k-ink);background:var(--k-card);border:2.5px solid var(--k-line);border-radius:999px;padding:9px 15px;text-decoration:none;
  box-shadow:3px 3px 0 var(--k-shadow);transition:transform .08s,box-shadow .08s;cursor:pointer}
.k-btn:hover{transform:translate(-1px,-1px);box-shadow:4px 4px 0 var(--k-shadow)}
.k-btn:active{transform:translate(3px,3px);box-shadow:0 0 0 var(--k-shadow)}
.k-btn.k-primary{background:var(--k-red);color:#fff;border-color:var(--k-line)}
.k-btn:focus-visible,.k-toggle:focus-visible{outline:3px solid var(--k-blue);outline-offset:3px}
.k-toggle{display:inline-flex;align-items:center;gap:2px;padding:4px;border:2.5px solid var(--k-line);border-radius:999px;background:var(--k-card);
  box-shadow:3px 3px 0 var(--k-shadow);cursor:pointer;color:var(--k-ink)}
.k-toggle span{display:grid;place-items:center;width:32px;height:28px;border-radius:999px}
.k-toggle svg{width:18px;height:18px}
:root[data-theme=light] .k-toggle .k-sun,:root:not([data-theme=dark]) .k-toggle .k-sun{background:var(--k-yellow);color:#111;box-shadow:inset 0 0 0 2px #111}
:root[data-theme=dark] .k-toggle .k-moon{background:var(--k-yellow);color:#111;box-shadow:inset 0 0 0 2px #111}
:root[data-theme=dark] .k-toggle .k-sun{background:none;box-shadow:none;color:var(--k-ink)}

/* hero: speed lines (dark) / halftone (light) */
.k-hero{position:relative;border:var(--k-bw) solid var(--k-line);border-radius:22px;background:var(--k-card2);box-shadow:var(--k-off) var(--k-off) 0 var(--k-shadow);
  overflow:hidden;padding:44px 40px 40px;margin:6px 0 10px;isolation:isolate}
.k-hero::before{content:"";position:absolute;inset:-40%;z-index:-1;pointer-events:none;
  background:repeating-conic-gradient(from 0deg at 72% 46%,var(--k-ray) 0deg 3.2deg,transparent 3.2deg 10deg);
  -webkit-mask-image:radial-gradient(circle at 72% 46%,transparent 0 6%,#000 26%,#000 60%,transparent 78%);
          mask-image:radial-gradient(circle at 72% 46%,transparent 0 6%,#000 26%,#000 60%,transparent 78%)}
.k-hero::after{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(circle,var(--k-halftone,rgba(217,72,59,.30)) 2.2px,transparent 2.6px) 0 0/15px 15px;
  -webkit-mask-image:radial-gradient(ellipse at 100% 0%,#000 0,transparent 58%);mask-image:radial-gradient(ellipse at 100% 0%,#000 0,transparent 58%)}
:root[data-theme=dark] .k-hero::after{--k-halftone:rgba(255,255,255,.06)}
.k-hero-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:28px;align-items:center}
.k-lede{font-size:17px;color:var(--k-ink2);max-width:600px;margin:18px 0 0}
.k-steps{display:flex;flex-wrap:wrap;gap:14px 26px;margin-top:28px}
.k-step{display:flex;align-items:center;gap:12px;min-width:0}
.k-step b{display:block;font:20px/1.1 var(--k-display);letter-spacing:.2px}
.k-step small{display:block;color:var(--k-mute);font-size:13px;margin-top:2px}
.k-art{position:relative;display:grid;place-items:center}
.k-art svg{width:100%;max-width:330px;height:auto;filter:drop-shadow(5px 5px 0 var(--k-shadow))}
.k-bubble{position:absolute;z-index:2;top:-6%;left:-14%;max-width:200px;background:#fff;color:#111;border:2.5px solid #111;border-radius:18px;padding:9px 13px;
  font:800 13px/1.3 var(--k-body);box-shadow:4px 4px 0 #111;transform:rotate(-3deg)}
.k-bubble::after{content:"";position:absolute;bottom:-16px;right:30px;border:7px solid transparent;border-top:9px solid #111}

/* type */
.k-h1{font:clamp(34px,5.6vw,64px)/1.03 var(--k-display);letter-spacing:.3px;color:var(--k-ink);text-shadow:3px 3px 0 var(--k-head-shadow);margin-top:16px}
.k-h2{font:clamp(24px,3.4vw,34px)/1.08 var(--k-display);color:var(--k-ink);text-shadow:2px 2px 0 var(--k-head-shadow)}
.k-h3{font:18px/1.15 var(--k-display);letter-spacing:.2px}
.k-tag{display:inline-block;background:var(--k-tag-bg);color:var(--k-tag-ink);font:italic 800 12.5px/1 var(--k-body);letter-spacing:.09em;
  text-transform:uppercase;padding:7px 12px 6px;transform:skewX(-10deg) rotate(-1.5deg);box-shadow:3px 3px 0 var(--k-red)}
.k-sech{display:flex;flex-direction:column;align-items:flex-start;gap:12px;margin:64px 0 22px}
.k-sech p{margin:0;color:var(--k-ink2);max-width:760px}

/* badge */
.k-badge{flex:none;display:grid;place-items:center;width:48px;height:48px;border-radius:50%;background:var(--k-red);color:#fff;
  font:22px/1 var(--k-display);border:3px solid #fff;box-shadow:0 0 0 2.5px var(--k-line),4px 4px 0 2.5px var(--k-blue)}

/* chip */
.k-chip{display:inline-block;background:var(--k-chip-bg);color:var(--k-chip-ink);font:800 10.5px/1 var(--k-body);letter-spacing:.1em;
  text-transform:uppercase;padding:5px 8px;border-radius:4px;white-space:nowrap}
.k-chip.k-red{background:var(--k-red);color:#fff}.k-chip.k-blue{background:var(--k-blue);color:#fff}.k-chip.k-ylw{background:var(--k-yellow);color:#111}

/* cards */
.k-card{background:var(--k-card);color:var(--k-ink);border:var(--k-bw) solid var(--k-line);border-radius:var(--k-r);
  box-shadow:var(--k-off) var(--k-off) 0 var(--k-shadow);padding:20px 22px;min-width:0}
.k-card.k-tilt-l{transform:rotate(-1deg)}.k-card.k-tilt-r{transform:rotate(1deg)}
.k-card.k-hl{background:var(--k-yellow);--k-ink:#111;--k-ink2:#2b2610;--k-mute:#4a4120;--k-line:#111;--k-ok:#0f5e37;--k-bad:#a3241c;--k-warn:#6b3f00;
  --k-chip-bg:#111;--k-chip-ink:#fff;--k-grid:rgba(0,0,0,.2);--k-link:#111;color:#111}
:root[data-theme=dark] .k-card.k-hl{border-color:#111;box-shadow:var(--k-off) var(--k-off) 0 var(--k-red)}
.k-card-h{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.k-grid{display:grid;gap:22px}
.k-g5{grid-template-columns:repeat(auto-fit,minmax(196px,1fr))}
.k-g3{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.k-g2{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}

/* stat tile */
.k-stat .k-num{font:48px/1 var(--k-display);letter-spacing:.5px;margin:14px 0 6px;font-variant-numeric:tabular-nums;white-space:nowrap}
.k-stat .k-num small{font-size:22px;color:var(--k-mute);margin-left:3px}
.k-stat .k-lbl{font-weight:800;font-size:14.5px}
.k-stat .k-det{font-size:13px;color:var(--k-mute);margin-top:6px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.k-st{display:inline-flex;align-items:center;gap:5px;font-weight:800;font-size:13px}
.k-st.ok{color:var(--k-ok)}.k-st.bad{color:var(--k-bad)}.k-st.warn{color:var(--k-warn)}
.k-st i{font-style:normal;display:grid;place-items:center;width:17px;height:17px;border-radius:50%;border:2px solid currentColor;font-size:10px;line-height:1}

/* tables */
.k-tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
.k-table{width:100%;border-collapse:collapse;font-size:14px}
.k-table th{text-align:left;font:800 11px/1.2 var(--k-body);text-transform:uppercase;letter-spacing:.08em;color:var(--k-ink);
  padding:10px 12px;border-bottom:var(--k-bw) solid var(--k-line);white-space:nowrap}
.k-table td{padding:11px 12px;border-bottom:1.5px dashed var(--k-grid);font-variant-numeric:tabular-nums;white-space:nowrap}
.k-table tr:last-child td{border-bottom:0}
.k-table .n{text-align:right}
.k-table .ours{background:var(--k-tint)}
.k-table th.ours{background:var(--k-yellow);color:#111}
.k-table .best{font-weight:800}
.k-table .best::before{content:"★ ";color:var(--k-red)}

/* key-value list */
.k-kv{display:grid;grid-template-columns:1fr auto;gap:0;font-size:14.5px}
.k-kv>div{padding:9px 0;border-bottom:1.5px dashed var(--k-grid)}
.k-kv>div:nth-child(odd){color:var(--k-ink2)}
.k-kv>div:nth-child(even){text-align:right;font-weight:800;font-variant-numeric:tabular-nums;padding-left:14px}
.k-kv>div:nth-last-child(-n+2){border-bottom:0}

/* legend + chart */
.k-legend{display:flex;gap:10px 18px;flex-wrap:wrap;font-size:13px;font-weight:600;color:var(--k-ink2);margin-bottom:14px;align-items:center}
.k-legend span{display:inline-flex;align-items:center;gap:7px}
.k-sw{width:18px;height:14px;border:2px solid var(--k-line);border-radius:3px;display:inline-block}
.k-chart{overflow-x:auto}.k-chart svg{width:100%;min-width:620px;height:auto;display:block}.k-chart text{font-family:var(--k-body)}
.k-chart .k-bar{transition:transform .1s}.k-chart g.k-row:hover .k-bar{filter:brightness(1.08)}
.k-chart g.k-row:hover .k-hit{fill:var(--k-tint)}
details.k-tv{margin-top:14px}details.k-tv summary{cursor:pointer;font-weight:800;font-size:13px;text-transform:uppercase;letter-spacing:.06em}

.k-live{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--k-ink2)}
.k-dot{width:12px;height:12px;border-radius:50%;background:#2fbf71;border:2px solid var(--k-line)}.k-dot.off{background:var(--k-yellow)}
.k-foot{margin:70px 0 40px;padding-top:22px;border-top:var(--k-bw) solid var(--k-line);color:var(--k-mute);font-size:13px;line-height:1.7}

@media (max-width:560px){
  .k-nav{order:3;width:100%;gap:8px}.k-btn{padding:8px 11px;font-size:11.5px}
}
@media (max-width:820px){
  .k-hero{padding:28px 20px 26px;border-radius:18px}
  .k-hero-grid{grid-template-columns:1fr}
  .k-art{order:-1;justify-self:center;width:62%;max-width:240px}
  .k-bubble{left:auto;right:-30%;top:-4%;max-width:150px;font-size:12px}
  .k-sech{margin-top:48px}
  .k-card{padding:16px}
  .k-stat .k-num{font-size:40px}
  .k-card.k-tilt-l,.k-card.k-tilt-r{transform:none}
}
@media (prefers-reduced-motion:reduce){.k-btn{transition:none}}

/* code cards with a copy button (arena, API docs) */
.k-code{position:relative;margin:12px 0 0;border:2.5px solid var(--k-line);border-radius:12px;background:#15142f;box-shadow:4px 4px 0 var(--k-shadow);overflow:hidden}
:root[data-theme=dark] .k-code{background:#0b0a24}
.k-code-h{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 8px 7px 12px;background:#24224f;border-bottom:2px solid #000;
  font:800 10.5px/1 var(--k-body);letter-spacing:.1em;text-transform:uppercase;color:#f5c542}
.k-code pre{margin:0;padding:13px 14px;font:12.5px/1.6 var(--k-mono);color:#f3efe3;white-space:pre-wrap;word-break:break-word;overflow-x:auto}
.k-code pre .c{color:#9b98d6}.k-code pre .s{color:#ffd76a}.k-code pre .k{color:#ff9d8f}
.k-copy{font:800 10.5px/1 var(--k-body);letter-spacing:.08em;text-transform:uppercase;color:#111;background:#f5c542;border:2px solid #000;border-radius:999px;
  padding:5px 10px;cursor:pointer;box-shadow:2px 2px 0 #000}
.k-copy:active{transform:translate(2px,2px);box-shadow:none}.k-copy:focus-visible{outline:3px solid var(--k-blue);outline-offset:2px}
.k-ic{font:600 .92em var(--k-mono);background:var(--k-tint);border:1.5px solid var(--k-grid);border-radius:5px;padding:0 5px;color:var(--k-ink);word-break:break-word}
.k-card.k-hl .k-ic{background:rgba(255,255,255,.6);border-color:rgba(0,0,0,.25)}

/* HTTP method pills */
.k-m{display:inline-grid;place-items:center;min-width:64px;font:800 11px/1 var(--k-body);letter-spacing:.08em;text-transform:uppercase;padding:6px 8px;
  border:2px solid #111;border-radius:6px;box-shadow:2px 2px 0 #111;color:#fff;background:#555}
.k-m.get{background:var(--k-blue)}.k-m.post{background:var(--k-yellow);color:#111}.k-m.delete{background:var(--k-red)}
.k-m.put,.k-m.patch{background:var(--k-coral);color:#111}
"""

CSS = TOKENS + COMPONENTS

# Theme bootstrap: runs in <head> before paint. Order: localStorage, URL hash (#theme=dark), OS preference.
THEME_HEAD_JS = """<script>(function(){var t=null;try{t=localStorage.getItem('alfred-theme')}catch(e){}
if(!t){var m=/theme=(dark|light)/.exec(location.hash);if(m)t=m[1]}
if(t!=='dark'&&t!=='light'){try{t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}catch(e){t='light'}}
document.documentElement.setAttribute('data-theme',t)})();</script>"""

THEME_TOGGLE_JS = """<script>(function(){var b=document.querySelectorAll('[data-k-toggle]');
function set(t){document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('alfred-theme',t)}catch(e){}
try{history.replaceState(null,'',location.pathname+location.search+'#theme='+t)}catch(e){}
b.forEach(function(x){x.setAttribute('aria-pressed',t==='dark'?'true':'false');x.setAttribute('aria-label',t==='dark'?'Switch to light mode':'Switch to dark mode')})}
b.forEach(function(x){x.addEventListener('click',function(){set(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark')})});
var cur=document.documentElement.getAttribute('data-theme');b.forEach(function(x){x.setAttribute('aria-pressed',cur==='dark'?'true':'false')});})();</script>"""

SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>'
MOON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.6A8.3 8.3 0 0 1 9.4 4a8.3 8.3 0 1 0 10.6 10.6z"/></svg>'


def e(x):
    return _html.escape(str(x))


def toggle_button():
    return (f'<button class="k-toggle" type="button" data-k-toggle aria-label="Toggle dark mode" title="Light / dark">'
            f'<span class="k-sun">{SUN}</span><span class="k-moon">{MOON}</span></button>')


def button(label, href, primary=False):
    return f'<a class="k-btn{" k-primary" if primary else ""}" href="{e(href)}">{e(label)}</a>'


def tag(text):
    return f'<span class="k-tag">{e(text)}</span>'


def chip(text, tone=""):
    return f'<span class="k-chip{" k-" + tone if tone else ""}">{e(text)}</span>'


def h1(text):
    return f'<h1 class="k-h1">{e(text)}</h1>'


def h2(text):
    return f'<h2 class="k-h2">{e(text)}</h2>'


def section_head(tag_text, title, lede=""):
    return f'<div class="k-sech">{tag(tag_text)}{h2(title)}{f"<p>{lede}</p>" if lede else ""}</div>'


def badge(n):
    return f'<span class="k-badge" aria-hidden="true">{e(n)}</span>'


def card(inner, cls="", label=None):
    """cls: any of k-hl (yellow highlight), k-tilt-l, k-tilt-r, k-stat."""
    aria = f' aria-label="{e(label)}"' if label else ""
    return f'<div class="k-card {cls}"{aria}>{inner}</div>'


def stat(label, value_html, detail_html="", chip_text="", cls="", chip_tone=""):
    top = f'<div class="k-card-h" style="margin:0"><span class="k-lbl">{e(label)}</span>{chip(chip_text, chip_tone) if chip_text else ""}</div>'
    return card(f'{top}<div class="k-num">{value_html}</div><div class="k-det">{detail_html}</div>', "k-stat " + cls)


def status(ok, label, tone=None):
    tone = tone or ("ok" if ok else "bad")
    ic = {"ok": "✓", "bad": "✕", "warn": "…"}[tone]
    return f'<span class="k-st {tone}"><i aria-hidden="true">{ic}</i>{e(label)}</span>'


def topbar(links=(), logo="ALFRED", logo_href="/dashboard", extra=""):
    nav = "".join(button(l, h, primary=p) for l, h, *rest in links for p in [bool(rest and rest[0])])
    return (f'<header class="k-wrap"><div class="k-top"><a class="k-logo" href="{e(logo_href)}">{e(logo)}</a>{extra}<span class="k-sp"></span>'
            f'<nav class="k-nav">{nav}</nav>{toggle_button()}</div></header>')


def _starburst(cx=100, cy=100, r1=97, r2=80, n=18):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.pi * i / n - math.pi / 2
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


def mascot(title="Alfred the butler-owl"):
    """Original character: a small butler-owl with a bow tie and a shield, inside a yellow starburst."""
    k = "#111"
    return f"""<svg viewBox="0 0 200 200" role="img" aria-label="{e(title)}"><title>{e(title)}</title>
<polygon points="{_starburst()}" fill="#f5c542" stroke="{k}" stroke-width="4" stroke-linejoin="round"/>
<g stroke="{k}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round">
<path d="M66 70 L60 40 L84 58 Z" fill="#2f5bd3"/><path d="M134 70 L140 40 L116 58 Z" fill="#2f5bd3"/>
<ellipse cx="100" cy="110" rx="46" ry="54" fill="#2f5bd3"/>
<ellipse cx="62" cy="120" rx="11" ry="24" fill="#24479f" transform="rotate(12 62 120)"/>
<ellipse cx="100" cy="138" rx="27" ry="23" fill="#fdf5e4"/>
<path d="M88 136 q6 5 12 0 q6 5 12 0 M88 146 q6 5 12 0 q6 5 12 0" fill="none" stroke-width="2.2"/>
<circle cx="82" cy="86" r="16" fill="#fff"/><circle cx="118" cy="86" r="16" fill="#fff"/>
<circle cx="85" cy="88" r="6.5" fill="{k}" stroke="none"/><circle cx="121" cy="88" r="6.5" fill="{k}" stroke="none"/>
<path d="M68 70 q14 -7 26 2 M106 72 q12 -9 26 -2" fill="none" stroke-width="3.5"/>
<path d="M93 100 L107 100 L100 111 Z" fill="#ee6a55"/>
<path d="M100 119 L80 109 L80 129 Z" fill="#d9483b"/><path d="M100 119 L120 109 L120 129 Z" fill="#d9483b"/>
<rect x="95" y="114" width="10" height="10" rx="2" fill="#d9483b"/>
<path d="M128 112 h34 v16 c0 16 -11 25 -17 28 c-6 -3 -17 -12 -17 -28 z" fill="#fff"/>
<path d="M137 129 l6 6 l11 -13" fill="none" stroke="#16794a" stroke-width="4.5"/>
<ellipse cx="86" cy="165" rx="9" ry="4.5" fill="#ee6a55"/><ellipse cx="114" cy="165" rx="9" ry="4.5" fill="#ee6a55"/>
</g><circle cx="80" cy="84" r="2.2" fill="#fff"/><circle cx="116" cy="84" r="2.2" fill="#fff"/></svg>"""


COPY_JS = """<script>(function(){function cp(t,b){function ok(){var o=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=o},1400)}
function fb(){var a=document.createElement('textarea');a.value=t;a.setAttribute('readonly','');a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();
try{document.execCommand('copy');ok()}catch(e){}document.body.removeChild(a)}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,fb)}else fb()}
document.addEventListener('click',function(ev){var b=ev.target.closest&&ev.target.closest('[data-copy]');if(!b)return;var el=document.getElementById(b.getAttribute('data-copy'));
if(el)cp(el.textContent,b)})})();</script>"""


def code(text, cid, label="curl", raw_html=False):
    """Dark code card with a label and a copy button (needs COPY_JS on the page). `cid` must be unique on the page."""
    body = text if raw_html else e(text)
    return (f'<div class="k-code"><div class="k-code-h"><span>{e(label)}</span><button type="button" class="k-copy" data-copy="{e(cid)}" '
            f'aria-label="Copy {e(label)}">Copy</button></div><pre id="{e(cid)}">{body}</pre></div>')


def method(m):
    return f'<span class="k-m {e(m.lower())}">{e(m.upper())}</span>'


def page(title, body, refresh=None, extra_css="", lang="en", head=""):
    """Full HTML document with fonts, theme tokens/components, theme bootstrap + toggle. `refresh` = seconds between
    reloads (JS reload keeps the URL hash, so the chosen theme survives even when localStorage is unavailable)."""
    reload_js = (f"<script>setTimeout(function(){{location.reload()}},{int(refresh) * 1000});</script>"
                 f'<noscript><meta http-equiv="refresh" content="{int(refresh)}"></noscript>') if refresh else ""
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title>{THEME_HEAD_JS}{FONTS}{head}<style>{CSS}{extra_css}</style></head>'
            f'<body>{body}{THEME_TOGGLE_JS}{reload_js}</body></html>')
