#!/usr/bin/env python3
"""Out-of-distribution PII eval on Gretel synthetic_pii_finance_multilingual TEST split (never used in training).
Only the PII types we target are scored (label-agnostic char recall). -> /vault/results/pii_ood_eval.json"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pii import evaluate, gliner_fn, rules, merge
from datasets import load_dataset
from gliner import GLiNER
from transformers import pipeline

MAP = {"name": "PERSON", "first_name": "PERSON", "last_name": "PERSON", "iban": "IBAN", "email": "EMAIL", "phone_number": "PHONE",
       "street_address": "ADDRESS", "date_of_birth": "DATE_OF_BIRTH", "credit_card_number": "CARD_NUMBER", "customer_id": "CUSTOMER_ID"}
ds = load_dataset("gretelai/synthetic_pii_finance_multilingual", split="test")
data = []
for r in ds:
    if r.get("language") not in ("English", "Italian"): continue
    sp = json.loads(r["pii_spans"]) if isinstance(r["pii_spans"], str) else r["pii_spans"]
    spans = [{"start": s["start"], "end": s["end"], "label": MAP[s["label"]]} for s in sp if s["label"] in MAP]
    if spans: data.append({"text": r["generated_text"][:2500], "spans": [s for s in spans if s["end"] <= 2500]})
    if len(data) >= 400: break
base = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1").to("cuda")
ft = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
pf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple", device=0, trust_remote_code=True)
pf_fn = lambda t: [{"start": e["start"], "end": e["end"], "label": e.get("entity_group")} for e in pf(t)]
res = {"n_docs": len(data), "source": "gretelai/synthetic_pii_finance_multilingual test split, English+Italian, our 8 target types"}
res["gliner_base"] = evaluate(gliner_fn(base, 0.3), data)
res["ours_finetuned+rules"] = evaluate(lambda t: merge(rules(t), gliner_fn(ft, 0.3)(t)), data)
res["openai_privacy_filter"] = evaluate(pf_fn, data)
res["ours+privacy_filter_ensemble"] = evaluate(lambda t: merge(merge(rules(t), gliner_fn(ft, 0.3)(t)), pf_fn(t)), data)
json.dump(res, open("/vault/results/pii_ood_eval.json", "w"), indent=1); print(json.dumps(res, indent=1))
