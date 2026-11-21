# data/real: open datasets (small derived samples)

Built by `data/scripts/build_real_samples.py` (seed 99). The raw downloads are not kept here. Total size is about 2.5 MB.

| File | Source | Licence | What it is |
|---|---|---|---|
| `cfpb_loan_narratives_sample.parquet` (3,551 rows) | CFPB Consumer Complaint Database, via the HF mirror [BEE-spoke-data/consumer-finance-complaints](https://huggingface.co/datasets/BEE-spoke-data/consumer-finance-complaints) (config `has-text`, shard 0, complaints received 2015-03 to 2024-02) | Public domain. The mirror is tagged CC0-1.0. The CFPB "considers previously published narratives to be in the public domain" ([CFPB, 14 Aug 2026](https://www.consumerfinance.gov/about-us/newsroom/the-cfpb-to-cease-discretionary-publication-of-complaint-narratives-and-visualizations/)); see also [data-use page](https://www.consumerfinance.gov/complaint/data-use/) | Narratives about debt collection, mortgages and loans. The CFPB has already scrubbed PII from them (`XXXX`). We dropped the company, state and ZIP columns. Columns: id, date_received, product, sub_product, issue, sub_issue, narrative, signal_label |
| `banking77_train.parquet`, `banking77_test.parquet` | [PolyAI/banking77](https://huggingface.co/datasets/PolyAI/banking77) | CC-BY-4.0. Attribution: Casanueva et al., 2020, "Efficient Intent Detection with Dual Sentence Encoders" | 13,083 customer banking queries in 77 intents. Unchanged copies |
| `eval_signals_cfpb.jsonl` (900 rows) | Derived from the two datasets above | Same licences as the sources | External test set for the signal reader. See the mapping rules in `docs/DATA.md` §4 |
| `eval_router_banking77.jsonl` (960 rows) | Derived from Banking77 test split | CC-BY-4.0 | Domain-shift test for the question router: 640 `knowledge` and 320 `action` |

**Not included, and why:**
- **Berka / PKDD'99:** no licence is stated on relational.fel.cvut.cz. We use only its schema as inspiration.
- **LendingClub:** the Kaggle copy carries a CC0 tag set by the uploader, but LendingClub's original terms are unverified.
- **Home Credit:** Kaggle competition data, which we treat as restricted.

We use only their *published aggregate ideas*, never their rows.

No row in this folder contains real personal data. CFPB narratives are de-identified by the CFPB, and Banking77 queries are anonymous.
