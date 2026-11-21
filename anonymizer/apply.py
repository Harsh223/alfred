#!/usr/bin/env python3
"""Run the fine-tuned anonymizer (GLiNER + rules) over the workspace documents.

GPU side:   apply.py predict /vault/data/workspace_docs.jsonl /vault/results/workspace_spans.jsonl
Local side: apply.py write   data/bank.duckdb runs/workspace_spans.jsonl
            -> replaces documents.anon_text with the model's output and records leakage on the live workspace.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))


def predict(inp, out):
    from gliner import GLiNER
    from pii import gliner_fn, rules, merge
    m = GLiNER.from_pretrained("/vault/models/gliner-bank").to("cuda"); f = gliner_fn(m)
    with open(out, "w") as w:
        for l in open(inp):
            d = json.loads(l); t = d["raw_text"]
            sp = merge(rules(t), f(t))
            w.write(json.dumps({"doc_id": d["doc_id"], "spans": [{**s, "value": t[s["start"]:s["end"]]} for s in sp]}, ensure_ascii=False) + "\n")


SANE = {  # a model-detected value must look like the thing it claims to be, otherwise it's not masked
    "PERSON": lambda v: len(v.split()) >= 2 and all(w[:1].isupper() for w in v.split() if w.isalpha()) and not any(w.lower() in {"office", "team", "bank", "customers", "policy"} for w in v.split()),
    "PHONE": lambda v: sum(ch.isdigit() for ch in v) >= 7 and ":" not in v,
    "CUSTOMER_ID": lambda v: any(ch.isdigit() for ch in v), "LOAN_ID": lambda v: any(ch.isdigit() for ch in v),
    "IBAN": lambda v: sum(ch.isdigit() for ch in v) >= 10, "ID_DOC": lambda v: any(ch.isdigit() for ch in v),
    "TAX_CODE": lambda v: sum(ch.isdigit() for ch in v) >= 5, "ADDRESS": lambda v: any(ch.isdigit() for ch in v),
}


def write(db, spans_path):
    import duckdb
    con = duckdb.connect(db)
    vault = {(lab, val): p for p, lab, val in con.execute("select pseudonym, label, real_value from vault").fetchall()}
    by_val = {val: p for (lab, val), p in vault.items()}
    cnt = {}
    pred = {json.loads(l)["doc_id"]: json.loads(l)["spans"] for l in open(spans_path)}
    tot = leak = 0
    for doc_id, kind, raw, gold in con.execute("select doc_id, kind, raw_text, spans from documents").fetchall():
        gold = json.loads(gold)
        sp = sorted((s for s in pred.get(doc_id, []) if kind != "policy" and SANE.get(s["label"], lambda v: True)(s["value"])), key=lambda s: s["start"])
        out, last = [], 0
        for s in sp:
            if s["start"] < last: continue
            v = s["value"]; p = vault.get((s["label"], v)) or by_val.get(v)
            if not p:
                cnt[s["label"]] = cnt.get(s["label"], 0) + 1; p = f"<{s['label']}_NEW_{cnt[s['label']]:03d}>"
                con.execute("insert into vault values (?,?,?)", [p, s["label"], v]); by_val[v] = p
            out.append(raw[last:s["start"]]); out.append(p); last = s["end"]
        anon = "".join(out + [raw[last:]])
        for g in gold:
            tot += 1; leak += int(g["value"] in anon)
        con.execute("update documents set anon_text = ? where doc_id = ?", [anon, doc_id])
    res = {"workspace_docs": len(pred), "gold_pii_values": tot, "leaked_values": leak, "workspace_leakage": round(leak / max(1, tot), 4)}
    json.dump(res, open(os.path.join(os.path.dirname(spans_path), "workspace_anon.json"), "w"), indent=1); print(res)


if __name__ == "__main__":
    {"predict": predict, "write": write}[sys.argv[1]](sys.argv[2], sys.argv[3])
