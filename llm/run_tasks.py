#!/usr/bin/env python3
"""Run a model (OpenAI-compatible endpoint) over task files; score; optionally keep gold-consistent outputs as SFT data.

  run_tasks.py eval   --url URL --model NAME --tag TAG [--headers JSON]      -> /vault/results/eval_<TAG>.json
  run_tasks.py distill --url URL --model NAME [--headers JSON]                -> /vault/data/sft.jsonl (teacher outputs that pass the scorer)
"""
import argparse, json, os, sys, time, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
from prompts import messages, score
from openai import OpenAI

ap = argparse.ArgumentParser()
ap.add_argument("mode"); ap.add_argument("--url"); ap.add_argument("--model"); ap.add_argument("--tag", default="")
ap.add_argument("--headers", default="{}"); ap.add_argument("--data", default="/vault/data/tasks"); ap.add_argument("--workers", type=int, default=64)
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--files", default=""); ap.add_argument("--out", default="/vault/data/sft.jsonl")
a = ap.parse_args()
cli = OpenAI(base_url=a.url, api_key="x", default_headers=json.loads(a.headers), timeout=300)


def call(task, inp):
    t0 = time.time()
    for att in range(3):
        try:
            r = cli.chat.completions.create(model=a.model, messages=messages(task, inp), temperature=0.2 if a.mode == "distill" else 0.0,
                                            max_tokens=400, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            return r.choices[0].message.content or "", time.time() - t0
        except Exception as e:
            err = str(e); time.sleep(3)
    return "", time.time() - t0


def load(name):
    rows = [json.loads(l) for l in open(f"{a.data}/{name}.jsonl")]
    return rows[: a.limit] if a.limit else rows


split = "test" if a.mode == "eval" else "train"
rows = [r for t in ("triage", "qa", "extract") for r in load(f"{t}_{split}")] if not a.files else [r for f in a.files.split(",") for r in load(f)]
for r in rows:
    if "task" not in r: r.update({"task": "signal", "input": {"text": r["text"]}, "gold": {"label": r["label"]}})
with cf.ThreadPoolExecutor(a.workers) as ex:
    outs = list(ex.map(lambda r: call(r["task"], r["input"]), rows))

agg, kept = {}, []
for r, (o, lat) in zip(rows, outs):
    s = score(r["task"], o, r["gold"])
    for k, v in s.items():
        if v is None: continue
        agg.setdefault(f"{r['task']}.{k}", []).append(v)
        if r.get("kind"): agg.setdefault(f"{r['task']}.{r['kind']}.{k}", []).append(v)
    agg.setdefault("latency_s", []).append(lat)
    ok = (s.get("exact", 1) == 1 and s.get("hallucinated", 0) == 0 and s.get("false_abstain", 0) == 0 and s.get("ans_correct", 1) == 1
          and s.get("key_recall", 1) >= 0.99 and s.get("valid_json", 1) == 1)
    if a.mode == "distill" and ok:
        kept.append({"messages": messages(r["task"], r["input"]) + [{"role": "assistant", "content": o.strip()}]})
res = {k: round(sum(v) / len(v), 4) for k, v in agg.items()} | {"n": len(rows), "model": a.model, "tag": a.tag}
os.makedirs("/vault/results", exist_ok=True)
if a.mode == "eval":
    json.dump(res, open(f"/vault/results/eval_{a.tag}.json", "w"), indent=1)
else:
    with open(a.out, "w") as f:
        for k in kept: f.write(json.dumps(k, ensure_ascii=False) + "\n")
    res["kept"] = len(kept); json.dump(res, open(f"/vault/results/distill_{a.tag or 'teacher_train'}.json", "w"), indent=1)
print(json.dumps(res, indent=1))
