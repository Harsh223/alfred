#!/usr/bin/env python3
"""PII anonymizer: fine-tune GLiNER on Lumen Bank + Gretel finance, add check-digit rules, evaluate vs baselines.

  pii.py train            -> /vault/models/gliner-bank
  pii.py eval             -> /vault/results/pii_eval.json  (base GLiNER, base+rules, fine-tuned, fine-tuned+rules, openai/privacy-filter)
Metric: character-level PII recall ("leakage" = 1 - recall, label-agnostic so every model is comparable), precision, span F1 (label-aware, GLiNER only).
"""
import json, os, re, sys, time, random
LABELS = ["PERSON", "TAX_CODE", "VAT_NUMBER", "IBAN", "CARD_NUMBER", "EMAIL", "PHONE", "ADDRESS", "DATE_OF_BIRTH", "ID_DOC", "CUSTOMER_ID", "LOAN_ID"]
NL = {"PERSON": "person", "TAX_CODE": "tax code", "VAT_NUMBER": "vat number", "IBAN": "iban", "CARD_NUMBER": "credit card number",
      "EMAIL": "email", "PHONE": "phone number", "ADDRESS": "address", "DATE_OF_BIRTH": "date of birth", "ID_DOC": "identity document number",
      "CUSTOMER_ID": "customer id", "LOAN_ID": "loan id"}
INV = {v: k for k, v in NL.items()}
D = "/vault/data/pii"

# ---------- deterministic validators (rules layer)
RX = {
    "IBAN": r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b",
    "TAX_CODE": r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b",
    "VAT_NUMBER": r"\bIT\d{11}\b",
    "EMAIL": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    "CARD_NUMBER": r"\b(?:\d{4} ){3}\d{4}\b",
    "CUSTOMER_ID": r"\bNDG\d{7}\b",
    "LOAN_ID": r"\b(?:MUT|PRE|FID)-\d{4}-\d{5}\b",
    "PHONE": r"(?:\+39 )?\b3\d{2} \d{3} \d{4}\b",
    "ID_DOC": r"\b(?:CA|AY|YA)\d{5}[A-Z]{2}\b",            # Italian electronic ID card (CIE) number
    "DATE_OF_BIRTH": r"(?<=Born on )\d{2}/\d{2}/\d{4}|(?<=born on )\d{2}/\d{2}/\d{4}|(?<=Date of birth: )\d{2}/\d{2}/\d{4}",
    "HEALTH": r"(?i)\b(?:in hospital|hospitali[sz]ed|surgery|cancer|chemotherapy|diagnos\w+|illness|sick leave|depression|disability|ricover\w+|malattia|chemioterapia|intervento chirurgico|invalidit\w+)\b",  # special-category data (GDPR Art. 9)
    # Italian postal address: "<street type> <name>, <number>[ Piano/Appartamento n], <CAP>, <city> (<PROV>)"
    "ADDRESS": r"\b(?:Via|Viale|Piazza|Piazzale|Corso|Contrada|Incrocio|Vicolo|Stretto|Canale|Borgo|Largo|Strada|Rotonda|Quartiere|Rione|Vico|Lungomare|Galleria|Salita|Calle)\s[^,\n]{2,40},\s\d+[^,\n]{0,25},\s\d{5},\s[^,\n()]+?(?:\s\([A-Z]{2}\))",
}
def iban_ok(s):
    s = s[4:] + s[:4]; return int("".join(str(int(c, 36)) for c in s)) % 97 == 1
def luhn_ok(s):
    d = [int(c) for c in s if c.isdigit()][::-1]
    return sum(x if i % 2 == 0 else sum(divmod(2 * x, 10)) for i, x in enumerate(d)) % 10 == 0
def rules(text):
    out = []
    for lab, rx in RX.items():
        for m in re.finditer(rx, text):
            v = m.group(0)
            if lab == "IBAN" and not iban_ok(v): continue
            if lab == "CARD_NUMBER" and not luhn_ok(v): continue
            out.append({"start": m.start(), "end": m.end(), "label": lab})
    return out

# ---------- data
def load(path): return [json.loads(l) for l in open(path)]
def to_gliner(ex):
    """char spans -> GLiNER token format"""
    toks = [(m.start(), m.end()) for m in re.finditer(r"\w+(?:[-'.@]\w+)*|[^\w\s]", ex["text"])]
    ner = []
    for s in ex["spans"]:
        ids = [i for i, (a, b) in enumerate(toks) if a >= s["start"] and b <= s["end"]]
        if ids: ner.append([ids[0], ids[-1], NL[s["label"]]])
    return {"tokenized_text": [ex["text"][a:b] for a, b in toks], "ner": ner}

def gretel_it(n=3000):
    """Gretel synthetic_pii_finance_multilingual, Italian + English rows, mapped to our labels where possible."""
    from datasets import load_dataset
    ds = load_dataset("gretelai/synthetic_pii_finance_multilingual", split="train")
    MAP = {"name": "PERSON", "first_name": "PERSON", "last_name": "PERSON", "iban": "IBAN", "email": "EMAIL", "phone_number": "PHONE", "street_address": "ADDRESS",
           "date_of_birth": "DATE_OF_BIRTH", "credit_card_number": "CARD_NUMBER", "company": None, "customer_id": "CUSTOMER_ID", "account_pin": None}
    rows = []
    for r in ds:
        if r.get("language") not in ("Italian", "English"): continue
        try: sp = json.loads(r["pii_spans"]) if isinstance(r["pii_spans"], str) else r["pii_spans"]
        except Exception: continue
        spans = [{"start": s["start"], "end": s["end"], "label": MAP[s["label"]]} for s in sp if MAP.get(s["label"])]
        if spans: rows.append({"text": r["generated_text"], "spans": spans})
        if len(rows) >= n: break
    return rows

# ---------- metrics
def char_set(spans): return {i for s in spans for i in range(s["start"], s["end"])}
def evaluate(pred_fn, data):
    tp = fp = fn = 0; t0 = time.time(); lab_tp = lab_n = 0
    for ex in data:
        pred = pred_fn(ex["text"]); g, p = char_set(ex["spans"]), char_set(pred)
        tp += len(g & p); fn += len(g - p); fp += len(p - g)
        gl = {(s["start"], s["end"], s["label"]) for s in ex["spans"]}; pl = {(s["start"], s["end"], s.get("label")) for s in pred}
        lab_tp += len(gl & pl); lab_n += len(gl)
    rec = tp / max(1, tp + fn); prec = tp / max(1, tp + fp)
    return {"char_recall": round(rec, 4), "char_precision": round(prec, 4), "leakage": round(1 - rec, 4), "char_f1": round(2 * rec * prec / max(1e-9, rec + prec), 4),
            "exact_span_label_acc": round(lab_tp / max(1, lab_n), 4), "ms_per_doc": round(1000 * (time.time() - t0) / len(data), 1)}

def merge(a, b):
    out = list(a)
    for s in b:
        if not any(not (s["end"] <= x["start"] or s["start"] >= x["end"]) for x in out): out.append(s)
    return out

def gliner_fn(model, thr=0.3):
    def f(text):
        ents = model.predict_entities(text, list(NL.values()), threshold=thr)
        return [{"start": e["start"], "end": e["end"], "label": INV.get(e["label"], e["label"])} for e in ents]
    return f

def main():
    from gliner import GLiNER
    import torch
    mode = sys.argv[1]
    if mode == "train":
        train = [to_gliner(x) for x in load(f"{D}/train.jsonl")]
        try:
            g = gretel_it(); train += [to_gliner(x) for x in g]; print("gretel rows", len(g), flush=True)
        except Exception as e: print("gretel skipped:", e, flush=True)
        random.Random(0).shuffle(train)
        m = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1").to("cuda")
        t0 = time.time()
        m.train_model(train_dataset=train, eval_dataset=train[:200], output_dir="/vault/models/gliner-bank-ckpt", max_steps=1500,
                      per_device_train_batch_size=16, learning_rate=3e-5, others_lr=5e-5, save_steps=500, logging_steps=50, report_to="none", bf16=True)
        m.save_pretrained("/vault/models/gliner-bank")
        json.dump({"train_rows": len(train), "minutes": round((time.time() - t0) / 60, 1)}, open("/vault/results/pii_train.json", "w"))
    elif mode == "eval":
        test = load(f"{D}/test.jsonl")
        res = {}
        base = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1").to("cuda")
        res["gliner_base"] = evaluate(gliner_fn(base), test)
        res["gliner_base+rules"] = evaluate(lambda t: merge(rules(t), gliner_fn(base)(t)), test)
        res["rules_only"] = evaluate(rules, test)
        ft = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda")
        res["gliner_finetuned"] = evaluate(gliner_fn(ft), test)
        res["gliner_finetuned+rules"] = evaluate(lambda t: merge(rules(t), gliner_fn(ft)(t)), test)
        try:
            from transformers import pipeline
            pf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple", device=0, trust_remote_code=True)
            res["openai_privacy_filter"] = evaluate(lambda t: [{"start": e["start"], "end": e["end"], "label": e.get("entity_group")} for e in pf(t)], test)
        except Exception as e:
            res["openai_privacy_filter"] = {"error": str(e)[:300]}
        res["n_test_docs"] = len(test)
        json.dump(res, open("/vault/results/pii_eval.json", "w"), indent=1); print(json.dumps(res, indent=1))

if __name__ == "__main__":
    main()
