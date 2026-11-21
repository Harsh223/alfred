#!/usr/bin/env python3
"""Download + derive the small open-data samples in data/real/ (see data/real/README.md for sources and licences).

  python data/scripts/build_real_samples.py [SRC_DIR]

SRC_DIR (default: a fresh temp dir) receives the raw downloads:
  - CFPB Consumer Complaint Database, HF mirror BEE-spoke-data/consumer-finance-complaints (config has-text, shard 0, CC0-1.0),
    filtered remotely with DuckDB httpfs to loan / mortgage / debt-collection products.
  - PolyAI/banking77 (CC-BY-4.0) train/test parquet.
Writes (all small):
  data/real/cfpb_loan_narratives_sample.parquet   stratified sample, only product/issue/narrative columns (company, state, ZIP dropped)
  data/real/banking77_{train,test}.parquet        unchanged copies (CC-BY-4.0, attribution in README)
  data/real/eval_signals_cfpb.jsonl               external test set for the signal reader (mapping rules below)
  data/real/eval_router_banking77.jsonl           domain-shift test set for the question router (subset of intents)
Deterministic (seed 99). Raw downloads are never committed.
"""
import json, os, re, random, sys, tempfile, urllib.request
import duckdb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "real"); os.makedirs(OUT, exist_ok=True)
SRC = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="realsrc_")
R = random.Random(99)
CFPB_URL = "https://huggingface.co/datasets/BEE-spoke-data/consumer-finance-complaints/resolve/main/has-text/train-00000-of-00003.parquet"
B77 = "https://huggingface.co/datasets/PolyAI/banking77/resolve/main/data/{split}-00000-of-00001.parquet"

con = duckdb.connect()
raw = os.path.join(SRC, "cfpb_loans.parquet")
if not os.path.exists(raw):
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute(f"""COPY (SELECT "Complaint ID" id, "Date received" date_received, Product product, "Sub-product" sub_product, Issue issue,
        "Sub-issue" sub_issue, "Consumer complaint narrative" narrative FROM '{CFPB_URL}'
        WHERE (Product ILIKE '%debt collection%' OR Product ILIKE '%mortgage%' OR Product ILIKE '%loan%')
          AND length("Consumer complaint narrative") BETWEEN 150 AND 2500) TO '{raw}' (FORMAT parquet)""")
for split in ("train", "test"):
    p = os.path.join(SRC, f"b77_{split}.parquet")
    if not os.path.exists(p): urllib.request.urlretrieve(B77.format(split=split), p)
    con.execute(f"COPY (SELECT * FROM '{p}') TO '{OUT}/banking77_{split}.parquet' (FORMAT parquet)")

rows = con.execute(f"SELECT id, date_received, product, sub_product, issue, sub_issue, narrative FROM '{raw}' ORDER BY id").fetchall()
cols = ["id", "date_received", "product", "sub_product", "issue", "sub_issue", "narrative"]
rows = [dict(zip(cols, r)) for r in rows]

# ------------------------------------------------------------------ mapping rules (documented in docs/DATA.md)
DEATH = re.compile(r"\bmy (late )?(father|mother|dad|mom|husband|wife|spouse|son|daughter|brother|sister|grand(mother|father|ma|pa)|parents?|aunt|uncle)\b[^.]{0,90}\b(passed away|passed|died|death|deceased)\b"
                   r"|\b(passed away|died)\b[^.]{0,60}\bmy (father|mother|dad|mom|husband|wife|spouse|parents?)\b", re.I)
ESTATE = re.compile(r"\b(estate|executor|executrix|probate|deceased|his (loan|account|debt|mortgage)|her (loan|account|debt|mortgage)|in (his|her) name|death certificate)\b", re.I)
HARD = re.compile(r"\b(lost (my|our) (job|income|employment)|laid off|unemploy\w*|furlough\w*|(reduc\w+|cut) (in )?(my |our )?(hours|income|pay|salary)|medical (bills|condition|emergency|issues|leave)"
                  r"|hospital\w*|surgery|cancer|disabilit\w+|covid|pandemic|(financial )?hardship|divorce\w*|can ?not afford|can't afford|unable to (make|afford|pay)"
                  r"|fell behind|fallen behind|behind on (my |our )?payments)\b", re.I)
DISP = re.compile(r"\b(dispute\w*|not mine|isn't mine|is not mine|already paid|paid (it )?in full|paid off|wrong amount|incorrect (amount|balance)|never owed|(don't|do not) owe|not my debt|identity theft)\b", re.I)
HARDSHIP_ISSUES = {"Struggling to pay mortgage", "Struggling to pay your loan", "Struggling to repay your loan", "Loan modification,collection,foreclosure"}
DISPUTE_PAIRS = {("Attempts to collect debt not owed", "Debt was paid"), ("Attempts to collect debt not owed", "Debt is not yours"),
                 ("Cont'd attempts collect debt not owed", "Debt is not mine"), ("Cont'd attempts collect debt not owed", "Debt was paid"),
                 ("False statements or representation", "Attempted to collect wrong amount"),
                 ("Dealing with your lender or servicer", "Don't agree with the fees charged"), ("Managing the loan or lease", "Billing problem")}
COMPLAINT_ISSUES = {"Communication tactics", "Threatened to contact someone or share information improperly"}
COMPLAINT_PAIRS = {("Dealing with your lender or servicer", "Problem with customer service"),
                   ("False statements or representation", "Impersonated attorney, law enforcement, or government official")}


def label(r):
    n, iss, sub = r["narrative"], r["issue"], r["sub_issue"]
    if DEATH.search(n) and ESTATE.search(n):
        return "deceased_notice", "narrative reports death of a family member AND refers to the deceased's debt/estate"
    if iss in HARDSHIP_ISSUES and HARD.search(n):
        return "hardship", f"CFPB issue '{iss}' AND explicit hardship cause in text"
    if (iss, sub) in DISPUTE_PAIRS and DISP.search(n) and not HARD.search(n):
        return "dispute", f"CFPB issue '{iss} / {sub}' AND disputes amount/ownership in text, no hardship cue"
    if (iss in COMPLAINT_ISSUES or (iss, sub) in COMPLAINT_PAIRS) and not DISP.search(n) and not HARD.search(n) and not DEATH.search(n):
        return "complaint", f"CFPB issue '{iss} / {sub}' (conduct of the lender/collector), no dispute/hardship cue"
    return None, None


RED = re.compile(r"\bX{2,}(?:[/\-]X{2,})*(?:\s+X{2,})*\b")
MONEY = re.compile(r"\{\$([\d,]+(?:\.\d\d)?)\}")
def to_bank_text(n):
    """Pseudonymised-looking text in the format our signal reader sees: CFPB 'XXXX' redactions -> <REDACTED_n>, {$x} -> EUR x."""
    k = [0]
    def red(m): k[0] += 1; return f"<REDACTED_{k[0]:04d}>"
    return MONEY.sub(lambda m: f"EUR {m.group(1)}", RED.sub(red, n)).strip()


by = {}
for r in rows:
    lab, why = label(r)
    if lab: by.setdefault(lab, []).append((r, why))
ev = []
for lab, items in sorted(by.items()):
    R.shuffle(items)
    for r, why in items[:150]:
        ev.append({"id": f"cfpb-{r['id']}", "source": "cfpb", "text": to_bank_text(r["narrative"]), "label": lab, "rule": why,
                   "cfpb": {"complaint_id": r["id"], "product": r["product"], "issue": r["issue"], "sub_issue": r["sub_issue"], "date_received": r["date_received"]}})

# Banking77 rows for the two labels CFPB cannot support defensibly (CFPB narratives are retrospective complaints to a regulator,
# not change-of-address notes or routine questions): change_of_details <- intent edit_personal_details; no_signal <- purely informational intents.
names = None
readme = os.path.join(SRC, "b77_README.md")
if not os.path.exists(readme): urllib.request.urlretrieve("https://huggingface.co/datasets/PolyAI/banking77/resolve/main/README.md", readme)
txt = open(readme).read()
names = re.findall(r"^\s+'?(\d+)'?:\s*([A-Za-z_?]+)\s*$", txt.split("names:")[1].split("splits:")[0], re.M)
NAMES = {int(i): n for i, n in names}
INFO = ["exchange_rate", "card_delivery_estimate", "top_up_limits", "supported_cards_and_currencies", "country_support", "fiat_currency_support",
        "age_limit", "card_acceptance", "atm_support", "disposable_card_limits", "visa_or_mastercard", "apple_pay_or_google_pay", "receiving_money",
        "order_physical_card", "getting_spare_card", "why_verify_identity"]
ACTION = ["cancel_transfer", "terminate_account", "edit_personal_details", "change_pin", "request_refund", "lost_or_stolen_card",
          "get_disposable_virtual_card", "card_swallowed"]
b77 = [dict(zip(["text", "label"], r)) | {"split": s} for s in ("train", "test")
       for r in con.execute(f"SELECT text, label FROM '{OUT}/banking77_{s}.parquet'").fetchall()]
for r in b77: r["intent"] = NAMES[r["label"]]
edit = [r for r in b77 if r["intent"] == "edit_personal_details"]; R.shuffle(edit)
info = [r for r in b77 if r["intent"] in INFO and r["split"] == "test"]; R.shuffle(info)
for i, r in enumerate(edit[:150]):
    ev.append({"id": f"b77-edit-{i:04d}", "source": "banking77", "text": r["text"], "label": "change_of_details", "rule": "Banking77 intent edit_personal_details"})
for i, r in enumerate(info[:150]):
    ev.append({"id": f"b77-info-{i:04d}", "source": "banking77", "text": r["text"], "label": "no_signal", "rule": f"Banking77 informational intent {r['intent']}"})
R.shuffle(ev)
with open(f"{OUT}/eval_signals_cfpb.jsonl", "w") as f:
    for e in ev: f.write(json.dumps(e, ensure_ascii=False) + "\n")

# router domain-shift set: customer-voice banking queries -> our employee-assistant intents (only two defensible buckets)
rt = [{"text": r["text"], "label": "knowledge", "banking77_intent": r["intent"]} for r in b77 if r["split"] == "test" and r["intent"] in INFO] + \
     [{"text": r["text"], "label": "action", "banking77_intent": r["intent"]} for r in b77 if r["split"] == "test" and r["intent"] in ACTION]
with open(f"{OUT}/eval_router_banking77.jsonl", "w") as f:
    for e in rt: f.write(json.dumps(e, ensure_ascii=False) + "\n")

# stratified narrative sample for the generator (email language) -- 600 per label + 1500 unlabelled loan/collection narratives
keep = {r["id"] for items in by.values() for r, _ in items[:600]}
other = [r["id"] for r in rows if r["id"] not in keep]; R.shuffle(other); keep |= set(other[:1500])
lab_of = {r["id"]: lab for lab, items in by.items() for r, _ in items}
con.execute("CREATE TABLE s(id BIGINT, label VARCHAR)"); con.executemany("INSERT INTO s VALUES (?,?)", [[i, lab_of.get(i)] for i in sorted(keep)])
con.execute(f"COPY (SELECT r.*, s.label AS signal_label FROM '{raw}' r JOIN s USING(id) ORDER BY id) TO '{OUT}/cfpb_loan_narratives_sample.parquet' (FORMAT parquet, COMPRESSION zstd)")
print(json.dumps({"cfpb_rows_scanned": len(rows), "labelled_pool": {k: len(v) for k, v in by.items()},
                  "eval_signals": {l: sum(e["label"] == l for e in ev) for l in sorted({e["label"] for e in ev})},
                  "eval_router": {l: sum(e["label"] == l for e in rt) for l in ("knowledge", "action")}, "sample_rows": len(keep)}, indent=1))
