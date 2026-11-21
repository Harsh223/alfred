#!/usr/bin/env python3
"""GLiNER v2: our bank data + Gretel finance + NVIDIA Nemotron-PII train split (CC-BY-4.0, commercial use OK).
Then compare v1 vs v2 (each + rules) on every test set. -> /vault/models/gliner-bank-v2, /vault/results/pii_v2_model.json"""
import json, os, random, sys, time, ast
sys.path.insert(0, os.path.dirname(__file__))
from pii import load, to_gliner, gretel_it, evaluate, gliner_fn, rules, merge, NL
from datasets import load_dataset
from gliner import GLiNER

NEMO = {"first_name": "PERSON", "last_name": "PERSON", "name": "PERSON", "email": "EMAIL", "phone_number": "PHONE", "street_address": "ADDRESS",
        "date_of_birth": "DATE_OF_BIRTH", "ssn": "TAX_CODE", "tax_id": "TAX_CODE", "national_id": "ID_DOC", "passport_number": "ID_DOC",
        "driver_license_number": "ID_DOC", "credit_debit_card": "CARD_NUMBER", "account_number": "IBAN", "iban": "IBAN", "customer_id": "CUSTOMER_ID"}
parse = lambda x: x if isinstance(x, list) else ast.literal_eval(x)
nemo = []
for r in load_dataset("nvidia/Nemotron-PII", split="train"):
    sp = [{"start": s["start"], "end": s["end"], "label": NEMO[s["label"]]} for s in parse(r["spans"]) if s["label"] in NEMO and s["end"] <= 2000]
    if sp: nemo.append({"text": r["text"][:2000], "spans": sp})
    if len(nemo) >= 12000: break
train = [to_gliner(x) for x in load("/vault/data/pii/train.jsonl")] + [to_gliner(x) for x in gretel_it(3000)] + [to_gliner(x) for x in nemo]
random.Random(1).shuffle(train); print("train rows", len(train), "nemotron", len(nemo), flush=True)
m = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1").to("cuda"); t0 = time.time()
m.train_model(train_dataset=train, eval_dataset=train[:200], output_dir="/root/gliner-v2-ckpt", max_steps=3500, per_device_train_batch_size=16,
              learning_rate=3e-5, others_lr=5e-5, save_steps=1000, logging_steps=100, report_to="none", bf16=True)
m.save_pretrained("/root/gliner-bank-v2"); mins = round((time.time() - t0) / 60, 1)
os.system("mkdir -p /vault/models/gliner-bank-v2 && cp -r /root/gliner-bank-v2/* /vault/models/gliner-bank-v2/")

src = open(os.path.join(os.path.dirname(__file__), "ood_eval2.py")).read().split("base = GLiNER")[0]
ns = {"__file__": os.path.join(os.path.dirname(__file__), "ood_eval2.py")}; exec(src, ns); sets = ns["sets"]
sets["bank_heldout"] = load("/vault/data/pii/test.jsonl")
v1 = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
res = {"train_rows": len(train), "train_minutes": mins}
for k, data in sets.items():
    res[k] = {"n": len(data), "v1+rules": evaluate(lambda t: merge(rules(t), gliner_fn(v1, 0.3)(t)), data),
              "v2+rules": evaluate(lambda t: merge(rules(t), gliner_fn(m, 0.3)(t)), data)}
    print(k, res[k]["v1+rules"]["char_recall"], "->", res[k]["v2+rules"]["char_recall"], flush=True)
json.dump(res, open("/vault/results/pii_v2_model.json", "w"), indent=1)
