"""HTML layout + CSS (server-rendered, no build step).

Dark, calm, fintech-grade design system (references: Mercury, Stripe, Revolut Business, Linear; see docs/UI_RESEARCH.md).
Tokens live in :root. Spacing on a 4px grid. Type scale 12 / 13 / 14 / 16 / 20 / 28. Every text colour meets WCAG AA on its surface.
"""
import html

CSS = """
:root{
--bg:#0b0c0e;--side:#0e0f12;--surface:#141518;--surface2:#1a1c20;--hover:#1f2126;--line:#25272d;--line2:#30333a;
--ink:#ececef;--ink2:#b4b8c1;--mute:#868b96;--faint:#5f646e;
--accent:#5e6ad2;--accent-h:#6c78e0;--accent-ink:#a9b1ff;--accent-bg:rgba(94,106,210,.16);
--ok:#4cc38a;--ok-bg:rgba(76,195,138,.12);--warn:#e8a952;--warn-bg:rgba(232,169,82,.12);--bad:#f2727f;--bad-bg:rgba(242,114,127,.12);--info:#7aa2ff;--info-bg:rgba(122,162,255,.12);
--r:10px;--r-sm:7px;--shadow:0 1px 0 rgba(255,255,255,.03) inset,0 1px 2px rgba(0,0,0,.35);
--font:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;--mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}html{color-scheme:dark}
body{margin:0;font:14px/1.5 var(--font);background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01"}
a{color:var(--accent-ink);text-decoration:none}a:hover{color:#c3c9ff}
.num,.stat .v,td.amt{font-variant-numeric:tabular-nums}
svg{flex:none;width:16px;height:16px}
/* ---------- shell */
.shell{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}
aside.side{background:var(--side);border-right:1px solid var(--line);padding:12px 10px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;overflow-y:auto}
.org{display:flex;align-items:center;gap:10px;padding:6px 8px 18px}
.org .mk{width:28px;height:28px;border-radius:8px;background:#ececef;color:#0b0c0e;display:grid;place-items:center;font-weight:750;font-size:14px;letter-spacing:-.3px}
.org .t{font-weight:600;font-size:14px;line-height:1.2}.org .s{color:var(--mute);font-size:12px;line-height:1.3}
.navlbl{font-size:11.5px;font-weight:500;color:var(--faint);padding:16px 10px 6px;letter-spacing:.2px}
.side a.nv{display:flex;align-items:center;gap:10px;height:34px;padding:0 10px;margin-bottom:1px;border-radius:var(--r-sm);color:var(--ink2);font-weight:500;font-size:13.5px;transition:background .12s,color .12s}
.side a.nv:hover{background:var(--hover);color:var(--ink)}.side a.nv.on{color:var(--ink);background:var(--surface2);box-shadow:inset 0 0 0 1px var(--line)}
.side a.nv svg{width:16px;height:16px;color:var(--mute)}.side a.nv.on svg{color:var(--ink)}
.side .cnt{margin-left:auto;background:var(--accent);color:#fff;border-radius:99px;padding:0 7px;font-size:11px;font-weight:650;line-height:18px;font-variant-numeric:tabular-nums}
.side .foot{margin-top:auto;padding:14px 10px 6px;display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--mute);line-height:1.45}
.side .foot .badge{display:inline-flex;align-items:center;gap:6px;color:var(--ink2);font-weight:500}
.side .foot .badge svg{width:14px;height:14px;color:var(--ok)}
/* ---------- top bar */
.top{height:56px;display:flex;align-items:center;gap:16px;padding:0 32px;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;background:rgba(11,12,14,.86);backdrop-filter:saturate(1.4) blur(10px)}
.crumb{font-size:13.5px;color:var(--mute);display:flex;align-items:center;gap:8px}.crumb b{color:var(--ink);font-weight:550}
.top .right{margin-left:auto;display:flex;align-items:center;gap:14px;font-size:13px;color:var(--mute)}
.pill{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 11px;border:1px solid var(--line);border-radius:99px;color:var(--ink2);font-size:12.5px;font-weight:500;background:var(--surface)}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--ok)}.pill.off::before{background:var(--warn)}
.me{display:flex;align-items:center;gap:10px;padding-left:14px;border-left:1px solid var(--line)}.me .nm{color:var(--ink);font-weight:550;line-height:1.25;font-size:13px}.me .rl{font-size:12px;color:var(--mute);line-height:1.25}
.me .rl a{color:var(--mute);text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:2px}.me .rl a:hover{color:var(--ink)}
.avatar{width:30px;height:30px;border-radius:50%;background:linear-gradient(140deg,#3a3f8f,#5e6ad2);display:grid;place-items:center;font-weight:650;font-size:11.5px;color:#fff;letter-spacing:.3px}
main{padding:32px 32px 96px}.wrap{max-width:1040px;margin:0 auto}.wrap.narrow{max-width:760px}.wrap.wide{max-width:1180px}
/* ---------- type + page header */
h1{font-size:28px;font-weight:650;letter-spacing:-.6px;line-height:1.2;margin:0}
h2{font-size:16px;font-weight:600;letter-spacing:-.1px;margin:0}
.ph{display:flex;align-items:flex-end;gap:16px;margin:4px 0 28px}.ph .tx{flex:1;min-width:0}.ph .acts{display:flex;gap:8px;align-items:center;flex:none}
.sub{color:var(--mute);margin:6px 0 0;font-size:14px;max-width:780px}.muted{color:var(--mute)}.small{font-size:12.5px}
.sec{display:flex;align-items:center;gap:8px;margin:36px 0 12px}.sec h2 .n{color:var(--mute);font-weight:500;margin-left:4px;font-variant-numeric:tabular-nums}.sec .r{margin-left:auto;display:flex;gap:8px;align-items:center}
.sec .hint{color:var(--mute);font-size:13px}
/* ---------- surfaces */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:20px 24px;box-shadow:var(--shadow)}
.card+.card{margin-top:12px}
.card .ch{display:flex;align-items:center;gap:10px;margin:-4px 0 12px}.card .ch h2{font-size:14px}.card .ch .r{margin-left:auto;display:flex;gap:8px;align-items:center}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}
.panel .ph2{display:flex;align-items:center;gap:10px;padding:14px 20px;border-bottom:1px solid var(--line)}
.panel .ph2 h2{font-size:14px}.panel .ph2 .n{color:var(--mute);font-weight:500;font-variant-numeric:tabular-nums}.panel .ph2 .r{margin-left:auto;display:flex;align-items:center;gap:10px;font-size:13px}
.list{display:flex;flex-direction:column}
.row{display:flex;gap:14px;align-items:flex-start;padding:16px 20px;border-top:1px solid var(--line);transition:background .12s}
.list>.row:first-child{border-top:0}.row:hover{background:rgba(255,255,255,.015)}
.ic{width:32px;height:32px;border-radius:8px;background:var(--surface2);border:1px solid var(--line);display:grid;place-items:center;flex:none;color:var(--ink2)}
.ic svg{width:16px;height:16px}.ic.warn{color:var(--warn);background:var(--warn-bg);border-color:transparent}.ic.bad{color:var(--bad);background:var(--bad-bg);border-color:transparent}
.ic.ok{color:var(--ok);background:var(--ok-bg);border-color:transparent}.ic.info{color:var(--info);background:var(--info-bg);border-color:transparent}
.row .tx{flex:1;min-width:0}.row .tt{font-weight:550;color:var(--ink);line-height:1.4}
.row .dd{color:var(--ink2);margin-top:3px;line-height:1.5}
.row .dd.clamp2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row .meta{margin-top:6px;font-size:12.5px;color:var(--mute);display:flex;gap:6px 14px;flex-wrap:wrap;align-items:center}
.row .meta details.pv summary{font-size:12.5px}.row .meta details.pv[open]{flex-basis:100%;order:9}.row .meta details.pv .preview{margin-top:8px}
.row .meta details.pv{display:flex;flex-wrap:wrap;align-items:center}.row .meta details.pv:not([open])::before{content:"·";margin-right:14px;color:var(--faint)}
.row .meta .sep::before{content:"·";margin-right:14px;color:var(--faint)}
.row .act{display:flex;gap:8px;align-items:center;flex:none;align-self:center}
/* stat strip */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}
.stat{padding:18px 22px;border-left:1px solid var(--line);color:inherit;display:block;transition:background .12s}.stat:first-child{border-left:0}
a.stat:hover{background:var(--hover);color:inherit}.stat .l{color:var(--mute);font-size:12.5px;font-weight:500;display:flex;align-items:center;gap:6px}
.stat .v{font-size:26px;font-weight:600;letter-spacing:-.6px;margin-top:6px;line-height:1.15;color:var(--ink)}.stat .v small{font-size:14px;color:var(--mute);font-weight:500;letter-spacing:0;margin-left:4px}
.stat .d{font-size:12.5px;color:var(--mute);margin-top:4px}.stat .go{font-size:12.5px;color:var(--accent-ink);margin-top:6px;display:inline-block}
.stat .v.warn{color:var(--warn)}.stat .v.ok{color:var(--ok)}
/* ---------- buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;height:34px;border:1px solid transparent;border-radius:var(--r-sm);padding:0 14px;font-weight:550;cursor:pointer;
background:var(--accent);color:#fff;font-size:13.5px;font-family:inherit;white-space:nowrap;transition:background .12s,border-color .12s,color .12s;box-shadow:0 1px 0 rgba(255,255,255,.12) inset}
.btn svg{width:15px;height:15px}.btn:hover{background:var(--accent-h);color:#fff}.btn:focus-visible,a:focus-visible,button:focus-visible{outline:2px solid var(--accent-ink);outline-offset:2px}
.btn.ok{background:var(--accent)}.btn.teal{background:var(--accent)}
.btn.ghost,.btn.secondary{background:var(--surface2);border-color:var(--line2);color:var(--ink);box-shadow:none}.btn.ghost:hover,.btn.secondary:hover{background:var(--hover);border-color:#3a3d45}
.btn.bad,.btn.quiet{background:transparent;border-color:transparent;color:var(--ink2);box-shadow:none}.btn.bad:hover,.btn.quiet:hover{color:var(--ink);background:var(--hover)}
.btn.sm{height:30px;padding:0 12px;font-size:13px}
.btn.approve{background:var(--surface2);border-color:var(--line2);color:var(--ink);box-shadow:none}.btn.approve svg{color:var(--ok)}
.btn.approve:hover{background:var(--ok-bg);border-color:rgba(76,195,138,.45);color:var(--ink)}
form.inline{display:inline}
.link{color:var(--accent-ink);font-weight:500;font-size:13px;display:inline-flex;align-items:center;gap:4px}.link svg{width:14px;height:14px}
/* ---------- tags / chips */
.tag{display:inline-flex;align-items:center;gap:6px;height:22px;border-radius:6px;padding:0 8px;font-size:12px;font-weight:550;background:var(--surface2);color:var(--ink2);border:1px solid var(--line);white-space:nowrap}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.9}
.tag.plain::before{display:none}
.tag.pending,.tag.exception{background:var(--warn-bg);color:var(--warn);border-color:transparent}
.tag.approved,.tag.executed,.tag.done,.tag.ok{background:var(--ok-bg);color:var(--ok);border-color:transparent}
.tag.rejected,.tag.denied{background:var(--bad-bg);color:var(--bad);border-color:transparent}
.tag.awaiting_approval,.tag.proposed{background:var(--accent-bg);color:var(--accent-ink);border-color:transparent}.tag.held{color:var(--ink2)}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.filters a{height:28px;display:inline-flex;align-items:center;padding:0 11px;border-radius:99px;border:1px solid var(--line);background:var(--surface);color:var(--ink2);font-size:12.5px;font-weight:500}
.filters a:hover{border-color:var(--line2);color:var(--ink)}.filters a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
/* pseudonyms + re-identified names */
.pseudo{background:var(--surface2);border:1px solid var(--line2);border-radius:5px;padding:0 5px;font-family:var(--mono);font-size:11.5px;color:var(--ink2);white-space:nowrap}
.reid{text-decoration:underline dotted rgba(232,169,82,.55);text-decoration-thickness:1px;text-underline-offset:3px;color:inherit;cursor:help}
a.cite{display:inline-flex;align-items:center;height:20px;background:var(--surface2);border:1px solid var(--line2);color:var(--ink2);border-radius:5px;padding:0 6px;font-size:11.5px;font-weight:550;margin:0 2px;font-family:var(--mono)}
a.cite:hover{color:var(--ink);border-color:#3a3d45}
a.cn{display:inline-grid;place-items:center;min-width:17px;height:17px;padding:0 4px;border-radius:5px;background:var(--surface2);border:1px solid var(--line2);color:var(--ink2);font-size:10.5px;font-weight:650;vertical-align:2px;margin:0 1px;font-variant-numeric:tabular-nums}
a.cn:hover{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink)}
/* ---------- tables (Mercury / Stripe style) */
.tbl{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:12px 16px;border-top:1px solid var(--line);vertical-align:middle;font-size:13.5px}
th{color:var(--mute);font-weight:500;font-size:12px;background:var(--surface);border-top:0;height:40px;padding-top:0;padding-bottom:0;white-space:nowrap}
tr:first-child td{border-top:0}th+th,td+td{}
tbody tr,table tr{transition:background .12s}table tr:hover td{background:rgba(255,255,255,.015)}
th.r,td.r,td.amt{text-align:right}td.amt{font-weight:550;color:var(--ink)}td .two{display:block;color:var(--mute);font-size:12px;margin-top:1px}
td.nowrap{white-space:nowrap}
/* ---------- banners, empty states */
.banner{display:flex;gap:12px;align-items:flex-start;border-radius:var(--r);padding:14px 16px;margin:0 0 16px;border:1px solid var(--line);color:var(--ink2);background:var(--surface)}
.banner svg{width:16px;height:16px;margin-top:2px}.banner.warn{background:var(--warn-bg);border-color:rgba(232,169,82,.25)}.banner.warn svg{color:var(--warn)}
.banner.bad{background:var(--bad-bg);border-color:rgba(242,114,127,.28)}.banner.bad svg{color:var(--bad)}.banner.ok{background:var(--ok-bg);border-color:rgba(76,195,138,.25)}
.banner b{color:var(--ink)}
.empty-st{text-align:center;padding:40px 24px}.empty-st .ic{margin:0 auto 12px;width:40px;height:40px;border-radius:10px}.empty-st .ic svg{width:18px;height:18px}
.empty-st .tt{font-weight:600;color:var(--ink);font-size:14.5px}.empty-st .dd{color:var(--mute);margin:4px auto 0;max-width:420px}.empty-st .btn{margin-top:16px}
/* ---------- inputs */
input,textarea,select{background:var(--surface);color:var(--ink);border:1px solid var(--line2);border-radius:var(--r-sm);font:inherit;transition:border-color .12s,box-shadow .12s}
input::placeholder{color:var(--faint)}
input:focus,textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.field{display:flex;gap:8px}.field input{flex:1;height:38px;padding:0 12px}
/* ---------- disclosure */
details>summary{cursor:pointer;color:var(--mute);list-style:none;font-size:13px;font-weight:500;display:inline-flex;align-items:center;gap:6px;user-select:none}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"";width:6px;height:6px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);transition:transform .15s;margin-right:2px}
details[open]>summary::before{transform:rotate(45deg)}details>summary:hover{color:var(--ink)}
details.more{margin-top:12px}
.mono{font-family:var(--mono);font-size:12px;white-space:pre-wrap;word-break:break-word;color:var(--ink2);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:8px;max-height:320px;overflow:auto}
.idc{font-family:var(--mono);font-size:12px;color:var(--mute)}
.clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.preview{margin-top:10px;padding:14px 16px;border-radius:8px;background:var(--bg);border:1px solid var(--line);color:var(--ink2);font-size:13.5px}
/* ---------- ask */
.ask{display:flex;flex-direction:column;min-height:calc(100vh - 56px - 40px);margin-bottom:-88px}.msgs{flex:1;padding-bottom:16px}
.askbar{display:flex;justify-content:flex-end;margin:-8px 0 8px}
.empty{text-align:center;padding:64px 0 24px}.empty .orb{width:44px;height:44px;border-radius:12px;margin:0 auto 18px;display:grid;place-items:center;background:var(--surface2);border:1px solid var(--line2);color:var(--accent-ink)}
.empty .orb svg{width:20px;height:20px}.empty h1{font-size:24px}.empty .sub{margin:8px auto 0;text-align:center}
.chips{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:32px;text-align:left}
.chips button{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;min-height:76px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:var(--r);padding:14px 16px;font:inherit;font-size:13.5px;cursor:pointer;text-align:left;line-height:1.4;transition:border-color .12s,background .12s}
.chips button:hover{border-color:var(--line2);background:var(--surface2)}.chips button svg{width:15px;height:15px;color:var(--mute)}
.q{display:flex;justify-content:flex-end;margin:28px 0 12px}.q div{background:var(--surface2);border:1px solid var(--line);border-radius:14px 14px 4px 14px;padding:9px 14px;max-width:78%;color:var(--ink)}
.a{margin:12px 0 28px;display:flex;gap:14px}.a .av{width:28px;height:28px;border-radius:8px;flex:none;background:var(--surface2);border:1px solid var(--line2);display:grid;place-items:center;color:var(--accent-ink);margin-top:1px}
.a .av svg{width:15px;height:15px}.a .body{flex:1;min-width:0}.a .body::before{content:"ALFRED";display:block;font-size:12.5px;color:var(--mute);font-weight:550;margin-bottom:4px}
.a .txt{color:var(--ink);font-size:14.5px;line-height:1.65}
.a .ft{margin-top:12px;font-size:12.5px;color:var(--mute);display:flex;gap:8px 14px;align-items:center;flex-wrap:wrap}
.a .ft .ok{display:inline-flex;align-items:center;gap:6px;color:var(--ok);font-weight:550}.a .ft .ok::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--ok)}
.a .ft .warn{display:inline-flex;align-items:center;gap:6px;color:var(--warn);font-weight:550}.a .ft .warn::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--warn)}
.a .ft .lock{display:inline-flex;align-items:center;gap:6px;color:var(--ink2);font-weight:550}.a .ft .lock svg{width:13px;height:13px}
.a.lock .txt{color:var(--ink2)}
.srcs{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.srcs a{display:inline-flex;align-items:center;gap:7px;max-width:100%;height:28px;padding:0 10px 0 4px;border-radius:7px;background:var(--surface);border:1px solid var(--line);color:var(--ink2);font-size:12.5px;transition:border-color .12s,color .12s}
.srcs a:hover{border-color:var(--line2);color:var(--ink)}.srcs a .k{display:grid;place-items:center;min-width:20px;height:20px;border-radius:5px;background:var(--surface2);font-size:11px;font-weight:650;color:var(--ink2)}
.srcs a .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:300px}
.typing{display:inline-flex;gap:4px;align-items:center;height:22px}.typing i{width:6px;height:6px;border-radius:50%;background:var(--mute);animation:blink 1.2s infinite ease-in-out}
.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
@keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
.composer{position:sticky;bottom:0;padding:16px 0 20px;background:linear-gradient(rgba(11,12,14,0),var(--bg) 28%)}
.composer form{display:flex;gap:8px;align-items:center;background:var(--surface);border:1px solid var(--line2);border-radius:14px;padding:8px 8px 8px 16px;box-shadow:0 8px 24px rgba(0,0,0,.35);transition:border-color .12s,box-shadow .12s}
.composer form:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg),0 8px 24px rgba(0,0,0,.35)}
.composer input{flex:1;border:0;background:transparent;padding:8px 0;font-size:14.5px;box-shadow:none!important}
.composer .btn{height:36px;width:36px;padding:0;border-radius:10px}
.composer .hint{text-align:center;font-size:12px;color:var(--mute);margin-top:10px}
/* ---------- brief */
.brief .row .dd{font-size:13.5px}
.brief .src{display:inline-flex;align-items:center;gap:5px;color:var(--mute);font-weight:500}.brief .src:hover{color:var(--ink)}.brief .src svg{width:13px;height:13px}
/* ---------- email */
.mail{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);max-width:760px;box-shadow:var(--shadow);overflow:hidden}
.mail .hd{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center}
.mail .hd .from{font-weight:600;color:var(--ink)}.mail .hd .meta{color:var(--mute);font-size:12.5px}
.mail .subj{padding:20px 24px 0;font-size:18px;font-weight:600;letter-spacing:-.2px}
.mail .body{padding:16px 24px 28px;font-size:14.5px;line-height:1.7;color:var(--ink2)}.mail .body b{color:var(--ink)}
/* ---------- login */
.loginwrap{max-width:500px;margin:6vh auto 0}
.loginwrap .lg{width:40px;height:40px;border-radius:10px;background:#ececef;color:#0b0c0e;display:grid;place-items:center;font-weight:750;font-size:18px;margin-bottom:20px}
.login{display:flex;flex-direction:column;margin-top:24px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;box-shadow:var(--shadow)}
.login form+form button{border-top:1px solid var(--line)}
.login button{width:100%;display:flex;align-items:center;gap:14px;text-align:left;background:transparent;color:var(--ink);border:0;padding:16px 20px;cursor:pointer;font:inherit;transition:background .12s}
.login button:hover{background:var(--hover)}.login .t{font-weight:600;font-size:14px}.login .tx{flex:1}
.login .chev{color:var(--faint)}.login .chev svg{width:16px;height:16px}
.notice{margin-top:20px;font-size:12.5px;color:var(--mute);display:flex;gap:8px;align-items:flex-start}.notice svg{width:14px;height:14px;margin-top:2px}
/* ---------- doc reader */
.reader{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:28px 32px;font-size:14.5px;line-height:1.7;color:var(--ink2);box-shadow:var(--shadow)}
/* ---------- responsive */
@media (max-width:1180px){.shell{grid-template-columns:212px minmax(0,1fr)}main{padding:28px 24px 96px}.top{padding:0 24px}}
@media (max-width:960px){.shell{grid-template-columns:64px minmax(0,1fr)}.side .lbl,.org .ot,.navlbl,.side .foot,.side .cnt{display:none}
 .side a.nv{justify-content:center;padding:0}.org{justify-content:center;padding:6px 0 18px}.me .tx2{display:none}.chips{grid-template-columns:1fr}
 .row{flex-wrap:wrap}.row .act{width:100%;justify-content:flex-end}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

IC = {  # 24px stroke icons (lucide-style, 1.75 stroke)
    "/today": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    "/chat": '<path d="M12 3c5 0 9 3.4 9 7.6s-4 7.6-9 7.6c-1 0-2-.1-2.9-.4L4 20l1.3-4C3.9 14.6 3 12.7 3 10.6 3 6.4 7 3 12 3z"/>',
    "/actions": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    "/autopilot": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "/memory": '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/><path d="M9 7h6"/>',
    "/audit": '<path d="M12 8v4l3 3"/><path d="M3.05 11a9 9 0 1 1 .5 4M3 4v5h5"/>',
    "/docs": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
    "/outbox": '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
    "/security": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "/email": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "shieldok": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="12" r="2"/><path d="M14 10h4M14 14h4"/>',
    "cal": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "server": '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/>',
    "up": '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    "trend": '<path d="m23 18-9.5-9.5-5 5L1 6"/><path d="M17 18h6v-6"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "send": '<path d="M12 19V5M5 12l7-7 7 7"/>',
    "spark": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "ext": '<path d="M7 17 17 7M8 7h9v9"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
    "play": '<path d="m6 4 14 8-14 8z"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    "chev": '<path d="m9 18 6-6-6-6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "dot": '<circle cx="12" cy="12" r="3"/>',
}
NAV = [("/today", "Today"), ("/chat", "Ask"), ("/actions", "Approvals"), ("/autopilot", "Autopilot"), ("/memory", "Memory")]
NAV2 = [("/security", "Security"), ("/audit", "Audit trail"), ("/docs", "Sources"), ("/outbox", "Outbox & exports"), ("/email", "Morning email")]
CRUMB = {"/today": "Home", "/chat": "Assistant", "/actions": "Work", "/autopilot": "Work", "/memory": "Knowledge", "/audit": "Records",
         "/docs": "Records", "/outbox": "Records", "/email": "Records", "/security": "Records"}


def svg(name, sw="1.75"):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{IC.get(name, IC["dot"])}</svg>')


def head(title, sub="", actions=""):
    """Page header: title, one-line explanation, actions on the right (one primary at most)."""
    return (f'<div class="ph"><div class="tx"><h1>{title}</h1>{f"<p class=sub>{sub}</p>" if sub else ""}</div>'
            f'{f"<div class=acts>{actions}</div>" if actions else ""}</div>')


def section(title, count=None, right="", id_=""):
    n = f'<span class="n">{count}</span>' if count is not None else ""
    return f'<div class="sec"{f" id={id_}" if id_ else ""}><h2>{title}{n}</h2>{f"<div class=r>{right}</div>" if right else ""}</div>'


def empty(icon, title, text="", action="", tone=""):
    return (f'<div class="empty-st"><div class="ic {tone}">{svg(icon)}</div><div class="tt">{title}</div>'
            f'{f"<div class=dd>{text}</div>" if text else ""}{action}</div>')


def panel(title, body, count=None, right=""):
    n = f' <span class="n">{count}</span>' if count is not None else ""
    return (f'<div class="panel"><div class="ph2"><h2>{title}{n}</h2>{f"<div class=r>{right}</div>" if right else ""}</div>'
            f'<div class="list">{body}</div></div>')


def page(title, body, active="", user=None, role_label=None, llm_status=None, pending=0, credit=True):
    side = ""
    if user:
        def nv(h, t):
            cnt = f"<span class=cnt>{pending}</span>" if h == "/actions" and pending else ""
            return f'<a class="nv {"on" if h == active else ""}" href="{h}" title="{t}">{svg(h)}<span class="lbl">{html.escape(t)}</span>{cnt}</a>'
        side = "".join(nv(h, t) for h, t in NAV if credit or h not in ("/actions", "/autopilot"))
        side += '<div class="navlbl">Records</div>' + "".join(nv(h, t) for h, t in NAV2 if credit or h not in ("/outbox", "/security"))
        side += ('<div class="foot"><span class="badge">' + svg("shieldok") + 'Runs on the bank\'s own servers</span>'
                 '<span>Synthetic data only: Lumen Bank and every person in it are fictional.</span>'
                 '<span><a href="/dashboard">Metrics dashboard</a> · <a href="/api/docs">API</a></span></div>')
    right = ""
    if user:
        on = bool(llm_status) and any(v == "configured" for v in llm_status.values())
        initials = "".join(w[0] for w in user.split()[:2]).upper()
        right = (f'<span class="pill {"" if on else "off"}" title="Language model status">{"AI on-prem" if on else "AI offline · safe mode"}</span>'
                 f'<span class="me"><span class="avatar">{initials}</span><span class="tx2"><div class="nm">{html.escape(user)}</div>'
                 f'<div class="rl">{html.escape(role_label or "")} · <a href="/logout">Switch</a></div></span></span>')
    crumb = CRUMB.get(active)
    top = (f'<div class="top"><div class="crumb">{f"<span>{crumb}</span><span>/</span>" if crumb else ""}<b>{html.escape(title)}</b></div>'
           f'<div class="right">{right}</div></div>')
    if not user:   # signed-out pages: no chrome, just the content
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Lumen Bank</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Lumen Bank</title><style>{CSS}</style></head><body>
<div class="shell"><aside class="side"><div class="org"><div class="mk">A</div><div class="ot"><div class="t">ALFRED</div><div class="s">Lumen Bank · Turin</div></div></div>
{side}</aside><div>{top}<main>{body}</main></div></div></body></html>"""


def tag(s, label=None):
    return f'<span class="tag {html.escape(str(s))}">{html.escape(label or str(s).replace("_", " "))}</span>'
