#!/usr/bin/env python3
"""Recall-oriented variants of the anonymizer + per-label recall. -> /vault/results/pii_variants.json"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pii import load, evaluate, gliner_fn, rules, merge, char_set, D
from gliner import GLiNER
from transformers import pipeline

test = load(f"{D}/test.jsonl")
ft = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
pf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple", device=0, trust_remote_code=True)
pf_fn = lambda t: [{"start": e["start"], "end": e["end"], "label": e.get("entity_group")} for e in pf(t)]
res = {}
for thr in (0.3, 0.2, 0.1):
    res[f"ft_thr{thr}+rules"] = evaluate(lambda t, thr=thr: merge(rules(t), gliner_fn(ft, thr)(t)), test)
best_thr = max((0.3, 0.2, 0.1), key=lambda x: res[f"ft_thr{x}+rules"]["char_f1"])
res["ensemble_ft+rules+privacy_filter"] = evaluate(lambda t: merge(merge(rules(t), gliner_fn(ft, best_thr)(t)), pf_fn(t)), test)
# per-label recall for the best single model
per = {}
f = lambda t: merge(rules(t), gliner_fn(ft, best_thr)(t))
for ex in test:
    p = char_set(f(ex["text"]))
    for s in ex["spans"]:
        g = set(range(s["start"], s["end"])); a = per.setdefault(s["label"], [0, 0]); a[0] += len(g & p); a[1] += len(g)
res["per_label_recall_best"] = {k: round(v[0] / v[1], 3) for k, v in sorted(per.items())}
res["best_thr"] = best_thr
json.dump(res, open("/vault/results/pii_variants.json", "w"), indent=1); print(json.dumps(res, indent=1))
