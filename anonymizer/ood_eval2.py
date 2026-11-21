#!/usr/bin/env python3
"""PII stress test v2 -> /vault/results/pii_v2.json
  hard:        our 600 new-format docs (signatures, spaced IBANs, lowercase/titled names, landlines, OCR forms, EN customers)
  nemotron:    nvidia/Nemotron-PII test split, finance domains (Banking/Mortgage/Credit/Brokerage), CC-BY-4.0
  ai4privacy:  ai4privacy/pii-masking-400k validation, Italian + English (evaluation only, non-commercial licence)
Only PII types we target are scored; label-agnostic character recall/precision."""
import json, sys, os, ast
sys.path.insert(0, os.path.dirname(__file__))
from pii import evaluate, gliner_fn, rules, merge, load
from datasets import load_dataset
from gliner import GLiNER
from transformers import pipeline

def parse(x): return x if isinstance(x, list) else (json.loads(x) if x.strip().startswith("[{\"") else ast.literal_eval(x))
sets = {"hard": [{"text": r["text"], "spans": r["spans"]} for r in load("/root/gdg/data/pii/hard.jsonl")]}
NEMO = {"first_name", "last_name", "name", "email", "phone_number", "street_address", "date_of_birth", "ssn", "credit_debit_card", "account_number",
        "bank_routing_number", "iban", "tax_id", "national_id", "customer_id", "passport_number", "driver_license_number"}
rows = []
for r in load_dataset("nvidia/Nemotron-PII", split="test"):
    if r["domain"] not in ("Banking", "Mortgage", "Credit", "Brokerage"): continue
    sp = [s for s in parse(r["spans"]) if s["label"] in NEMO]
    if sp: rows.append({"text": r["text"][:3000], "spans": [s for s in sp if s["end"] <= 3000]})
    if len(rows) >= 400: break
sets["nemotron_finance"] = rows
A4 = {"GIVENNAME", "SURNAME", "EMAIL", "TELEPHONENUM", "STREET", "BUILDINGNUM", "ZIPCODE", "IDCARDNUM", "TAXNUM", "CREDITCARDNUMBER", "DATEOFBIRTH",
      "SOCIALNUM", "PASSPORTNUM", "DRIVERLICENSENUM", "ACCOUNTNUM", "IBAN"}
for lang in ("it", "en"):
    rows = []
    for r in load_dataset("ai4privacy/pii-masking-400k", split="validation"):
        if r["language"] != lang: continue
        sp = [s for s in parse(r["privacy_mask"]) if s["label"] in A4]
        if sp: rows.append({"text": r["source_text"], "spans": sp})
        if len(rows) >= 300: break
    sets[f"ai4privacy_{lang}"] = rows

base = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1").to("cuda")
ft = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
pf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple", device=0, trust_remote_code=True)
pf_fn = lambda t: [{"start": e["start"], "end": e["end"], "label": e.get("entity_group")} for e in pf(t)]
systems = {"gliner_base": gliner_fn(base, 0.3), "ours_ft+rules": lambda t: merge(rules(t), gliner_fn(ft, 0.3)(t)), "openai_privacy_filter": pf_fn,
           "ours+privacy_filter": lambda t: merge(merge(rules(t), gliner_fn(ft, 0.3)(t)), pf_fn(t))}
res = {}
for sname, data in sets.items():
    res[sname] = {"n": len(data)}
    for k, f in systems.items():
        res[sname][k] = evaluate(f, data); print(sname, k, res[sname][k]["char_recall"], flush=True)
json.dump(res, open("/vault/results/pii_v2.json", "w"), indent=1)
