#!/usr/bin/env python3
"""Production masker = ours (GLiNER-ft + rules) ∪ OpenAI privacy-filter restricted to identity categories (no dates/URLs,
so policy deadlines and amounts stay readable). Evaluates on all 5 test sets + checks policies are untouched.
-> /vault/results/pii_ensemble.json and /vault/results/workspace_spans_ensemble.jsonl"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pii import evaluate, gliner_fn, rules, merge, load
from gliner import GLiNER
from transformers import pipeline
import importlib.util
spec = importlib.util.spec_from_file_location("v2", os.path.join(os.path.dirname(__file__), "ood_eval2.py"))

ft = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
pf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple", device=0, trust_remote_code=True)
labels_seen = {}
DROP = ("date", "url")
def pf_fn(t):
    out = []
    for e in pf(t):
        g = str(e.get("entity_group", "")); labels_seen[g] = labels_seen.get(g, 0) + 1
        if not any(d in g.lower() for d in DROP): out.append({"start": e["start"], "end": e["end"], "label": g})
    return out
ens = lambda t: merge(merge(rules(t), gliner_fn(ft, 0.3)(t)), pf_fn(t))

# reuse the dataset loading from ood_eval2 without re-running its models
src = open(os.path.join(os.path.dirname(__file__), "ood_eval2.py")).read().split("base = GLiNER")[0]
ns = {"__file__": os.path.join(os.path.dirname(__file__), "ood_eval2.py")}; exec(src, ns); sets = ns["sets"]
sets["gretel_ood"] = None
from datasets import load_dataset
MAP = {"name", "first_name", "last_name", "iban", "email", "phone_number", "street_address", "date_of_birth", "credit_card_number", "customer_id"}
g = []
for r in load_dataset("gretelai/synthetic_pii_finance_multilingual", split="test"):
    if r.get("language") not in ("English", "Italian"): continue
    sp = json.loads(r["pii_spans"]) if isinstance(r["pii_spans"], str) else r["pii_spans"]
    sp = [s for s in sp if s["label"] in MAP and s["end"] <= 2500]
    if sp: g.append({"text": r["generated_text"][:2500], "spans": sp})
    if len(g) >= 400: break
sets["gretel_ood"] = g
sets["bank_heldout"] = load("/vault/data/pii/test.jsonl")
res = {k: {"n": len(v), "ensemble_no_dates": evaluate(ens, v)} for k, v in sets.items()}
# policies must stay readable: nothing masked inside the 7 policy documents' numbers/dates
pol = [json.loads(l) for l in open("/vault/data/workspace_docs.jsonl") if json.loads(l)["doc_id"].startswith("POL")]
res["policy_masks"] = {d["doc_id"]: [d["raw_text"][s["start"]:s["end"]] for s in ens(d["raw_text"])] for d in pol}
res["privacy_filter_labels_seen"] = labels_seen
json.dump(res, open("/vault/results/pii_ensemble.json", "w"), indent=1)
with open("/vault/results/workspace_spans_ensemble.jsonl", "w") as w:
    for l in open("/vault/data/workspace_docs.jsonl"):
        d = json.loads(l); t = d["raw_text"]
        w.write(json.dumps({"doc_id": d["doc_id"], "spans": [{**s, "label": s["label"] if s["label"] in ("PERSON","TAX_CODE","VAT_NUMBER","IBAN","CARD_NUMBER","EMAIL","PHONE","ADDRESS","DATE_OF_BIRTH","ID_DOC","CUSTOMER_ID","LOAN_ID") else "PII", "value": t[s["start"]:s["end"]]} for s in ens(t)]}, ensure_ascii=False) + "\n")
print(json.dumps({k: (v.get("ensemble_no_dates", {}).get("char_recall"), v.get("ensemble_no_dates", {}).get("char_precision")) for k, v in res.items() if isinstance(v, dict) and "n" in v}, indent=1))
print(json.dumps(res["policy_masks"], indent=1))
