# Lumen Bank data: what is synthetic, what is real-derived, and how it is calibrated

Status as of 21 Nov 2026. The challenge rule is no real client or personal data. Every person, company and bank account here is fictional. What is real is the **formats**, the **calibration figures** and the **language** of customer emails, which comes from public-domain complaint narratives.

There are two banks:

| | `data/bank.duckdb` (live demo, untouched) | `runs/realism/bank.duckdb` (this work) |
|---|---|---|
| Generator | `data/scripts/gen_bank.py` (seed 7) | `data/scripts/gen_realism.py` (seed 11), run as `OUT=runs/realism python data/scripts/gen_realism.py` |
| Customers / loans | 400 / 497 | 2,400 / 2,988 |
| Share of loans in arrears | 22% (arbitrary) | **4.6%**: personal loans 6.1%, mortgages 2.2%, SME loans 4.8% |
| Arrears cases | 99 (exceptions 54%) | 136 (exceptions 32%, straight-through 68%) |
| Payments | 18 rows, written directly | 874 rows **parsed from 27 ISO 20022 camt.054.001.08 XML files** |
| Customer emails | template sentences | 21 of 30 use sentences from real CFPB narratives with the same signal |
| Identifiers | Faker CF / IBAN (random ABI, which may collide with real banks) | Codice fiscale built with the real algorithm (name, date of birth, sex, Belfiore code, check char). IBAN with real CIN + mod-97 but **fictional ABI 99xxx**. P.IVA with a valid check digit |
| Documents | 86 | 102, including 3 new realistic procedures (complaints/ABF, bereavement, forbearance) |

The schema is identical: the same 12 tables and the same column types. All conventions are kept:
- the 6 planted events (covenant, AML, two batch failures, injection, wrong fact);
- the AML ticket has `department='aml'`;
- the AML customer has an arrears case whose `cases_gold` row is `hold_for_human / aml_alert_open` (CASE-0076);
- customer NDG0000002 is still "Ivo Bonomo", the fictional name the test battery uses.

## 1. Validation (separate app instance on port 8082, live demo untouched)

```
BANK_DB=runs/realism/bank.duckdb APP_DB=runs/realism/app_bank.duckdb OUTBOX=runs/realism/outbox uvicorn app.main:app --port 8082
tests/jury_checks.py   -> 11/11 PASS   (runs/realism/runs/jury_checks.json)
tests/human_battery.py -> 57/57 PASS   (runs/realism/runs/human_battery.json)
```

In the autopilot run on the realistic book, 136 cases came in. 43 stopped as exceptions, which matches the gold labels exactly. The other 93 produced 125 proposed actions, and no action was proposed on any exception. The run reports 17.0 h saved per day under the stated 12-minutes-per-case assumption.

## 2. Calibration figures (sources)

| Parameter | Value used | Basis |
|---|---|---|
| NPL ratio context | Gross NPL ratio 2.5% (June 2026). Households 1.7%, firms 4.6% | Bank of Italy, *Rapporto sulla stabilità finanziaria* 2/2026, appendix Tav. A3/A4 ([RSF-App](https://www.bancaditalia.it/pubblicazioni/rapporto-stabilita/2026-2/RSF_2_2026_appendice.pdf)) |
| Default-entry rates | Mortgages 0.6%, consumer credit 2.5%, firms 1.5% (Q2 2026, annualised) | RSF 2/2026 ([RSF](https://www.bancaditalia.it/pubblicazioni/rapporto-stabilita/2026-2/RSF_2_2026.pdf)) |
| Household credit default rate | 1.5% total, mortgages 0.4% (Mar 2026) | Assofin-CRIF-Prometeia Observatory, reported by [Teleborsa, 25 Jun 2026](https://www.teleborsa.it/News/2026/06/25/assofin-crif-e-prometeia-il-credito-alle-famiglie-riparte-tra-prestiti-mutui-e-digitale-101.html) |
| SME default rate | 3.0% (end 2025) | CRIF, reported by [Teleborsa, 8 Jun 2026](https://www.teleborsa.it/AMP/News/2026/06/08/crif-prestiti-alle-imprese-11percent-default-in-aumento-59.html) |
| **Arrears probability** (≥1 missed instalment, stock) | Mortgages 2%, personal loans 6%, SME loans 5% | **Assumption.** Early arrears are a multiple of the default-entry rates above, because most 1–30 dpd cases self-cure. The ordering follows the data: consumer > SME > mortgage. No public Italian 30+ dpd stock figure for households was found |
| Days-past-due mix of arrears cases | Months unpaid 1/2/3/4/5/6 = 55/22/12/5/4/2%. Realised buckets: 82 / 26 / 14 / 14 (1-30 / 31-60 / 61-90 / 90+) | **Assumption** (roll-rate shape). No public Italian dpd split was found |
| Mortgage amount | Lognormal, median €140k, realised mean €158k | CRIF Barometro: average requested mortgage €153.4k (2025), €154.0k (H1 2026) ([CRIF](https://www.crif.it/media/2clfilnt/2026-barometro-07-infografica-crif.pdf), figure from search summary) |
| Mortgage term / rate | 20–30 y (mode 25–30). New loans 2.4–4.3%; 2021-and-earlier vintages 1.1–2.3% | CRIF (25–30 y most requested, H1 2025). Average TAEG 3.99% in Aug 2026 (Bank of Italy data, reported by [Edilizia.com](https://www.edilizia.com/mutui/mutui-casa-taeg-agosto-2026-3-99/)) |
| Personal loan amount / term / rate | Median €10.5k, realised mean €12.7k. Terms 36–96 months. Rates 6.5–12.5% (mean 9.5%) | CRIF: average €11.9k (2025), €12.3k (Q1 2026); 52.8% of requests are over 5 years. Total cost of consumer credit 10.8% in Sep 2026 (RSF 2/2026) |
| SME loan | €25k–400k, 3.6–7.5% | Firms' new loans 3.8% excluding overdrafts (RSF 2/2026). Sizes are an assumption (no public figure found) |
| Exception rates among arrears customers | Deceased 1.5%, vulnerable 5%, forbearance 6%, open complaint 4%, dispute 3%, partial/unmatched payment in last 10 days 10%. AML: 1 case | **Assumptions**, set as small shares so that most of the book goes straight through. The old book had 54% exceptions, which is unrealistic. Floored at 1 so every policy path is exercised |
| Customer base | 88% retail / 12% SME. Residents of Turin province plus Asti, Cuneo and Alessandria. About 12% born abroad (Romania, Morocco, Albania; Romanian names from Faker ro_RO) | Assumption for a Turin regional bank |

## 3. Real formats used

- **ISO 20022 camt.054.001.08** (`BkToCstmrDbtCdtNtfctn`), namespace `urn:iso:std:iso:20022:tech:xsd:camt.054.001.08`. Each credit entry carries:
  - `Amt@Ccy`, `CdtDbtInd=CRDT` and `Sts/Cd=BOOK`;
  - `BookgDt/Dt`, `ValDt/Dt` and `AcctSvcrRef`;
  - `BkTxCd` PMNT/RCDT/ESCT;
  - `TxDtls/Refs/EndToEndId`, `RltdPties/Dbtr/Pty/Nm`, `DbtrAcct/Id/IBAN` and `RmtInf/Ustrd`.

  Paths are checked against the CGI-MP camt.054.001.08 usage guideline. The generator writes one file per booking day (`runs/realism/camt054/`), then **parses** the files to build `payments`. It matches each credit in three steps:
  1. a loan ID in the remittance text;
  2. otherwise the debtor IBAN;
  3. otherwise the borrower's name in the remittance text.

  Credits matched to a customer but not to a loan stay unmatched (`loan_id` NULL, 14 of them). Credits matched to no one go to suspense (`customer_id` NULL, 3 of them). Partial or unmatched credits in the last 10 days set `recent_payment`, which is the SPEC exception. CBI (CBI S.c.p.a., promoted by ABI) sets the Italian interbank standards; CBI Globe is the Italian PSD2 hub.
- **Italian IBAN:** IT + 2 check digits + CIN + ABI(5) + CAB(5) + account(12), 27 characters. The CIN uses the official odd/even tables and the check digits use mod-97. ABI codes are assigned to real banks by the Bank of Italy, so Lumen Bank uses **99021** and the "other banks" use 99034/99047/99058/99063. We found no source that documents a reserved range. The codes should be checked against the [Bank of Italy register](https://www.bancaditalia.it/servizi-cittadino/servizi/albi-elenchi/) before any external use (UNVERIFIED as unassigned).
- **Codice fiscale:** surname and name consonant rules, YY, month letter, day (+40 for women), Belfiore code of the birth municipality or foreign country (L219 Torino, Z129 Romania, …), and the check character.
- **Collections conventions,** written into the procedures:
  - the formal reminder is the *messa in mora* (art. 1219 c.c.), and a demand under art. 1454 c.c. gives at least 15 days;
  - a *preavviso* is sent before a first late payment is reported to a credit bureau (SIC code of conduct, art. 5 c.6; Garante provision 163/2019, [docweb 9141941](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/9141941));
  - complaints (*reclami*) are answered within 60 days, or 15 business days for payment services, and can then go to the ABF. Source: a secondary bank guide ([Poste](https://www.poste.it/resources/bancoposta/pdf/trasparenza/guida_arbitro_finanziario.pdf)); the Bank of Italy primary text was not checked.
- **EBA NPL data templates (2017):** these are loan-level templates for NPL transactions. They are not used directly, but our loan / installment / payment split follows the same borrower, loan and cash-flow separation.

The key policy sentences that the demo relies on are unchanged (€250k vs €150k, 33%, €15 PEC fee, 90+ to legal, RICONC-02, 25/11/2026, 8:30). New sentences avoid conflicting numbers and avoid topics the tests expect the Brain to refuse, such as the CEO, Spain or Saturday hours.

## 4. External test sets for the models (`data/real/`)

### `eval_signals_cfpb.jsonl`

There are 900 rows, 150 per label. Fields: `text`, `label`, `rule`, `source` and CFPB metadata. In `text`, CFPB redactions `XXXX` become `<REDACTED_n>` and `{$x}` becomes `EUR x`, so the text looks like our pseudonymised input. The rules are checked in order:

| Label | Source | Rule (all conditions required) |
|---|---|---|
| `deceased_notice` | CFPB | The text reports the death of a named relative ("my father … passed away") **and** refers to the deceased's debt or estate (estate, executor, probate, death certificate, "his loan" …). This rule is checked first |
| `hardship` | CFPB | Issue ∈ {Struggling to pay mortgage, Struggling to pay/repay your loan, Loan modification/collection/foreclosure} **and** an explicit cause in the text (lost job, laid off, medical, hospital, divorce, covid, can't afford, fell behind …) |
| `dispute` | CFPB | (Issue, sub-issue) ∈ {Debt was paid, Debt is not yours/mine, Attempted to collect wrong amount, Don't agree with the fees charged, Billing problem} **and** dispute wording in the text (not mine, already paid, wrong amount, dispute …) **and** no hardship cue |
| `complaint` | CFPB | Issue ∈ {Communication tactics, Threatened to contact someone / share information improperly} or sub-issue ∈ {Problem with customer service, Impersonated attorney …}, which are complaints about conduct, **and** no dispute, hardship or death cue |
| `change_of_details` | Banking77 | Intent `edit_personal_details` |
| `no_signal` | Banking77 | Purely informational intents (exchange_rate, card_delivery_estimate, top_up_limits, country_support, atm_support …) |
| `payment_promise` | — | **Not included.** CFPB narratives look back on past events in a report to a regulator, and "I offered to pay" there is part of a grievance, not a commitment to the lender. No defensible mapping exists, so this label stays covered only by the synthetic `data/signals/test.jsonl` |

Caveats:
- CFPB texts are US English and long (150–2,500 characters). Many are complaints by nature, so precision on `complaint` vs `dispute` is the hard part. Treat this set as a stress test, not as an in-distribution score.
- The texts name real US companies, as published by the CFPB. That is acceptable in an evaluation file. They are **never** copied into Lumen Bank documents: the generator keeps only sentences with no capitalised proper nouns, no redactions and no US-specific terms.

### `eval_router_banking77.jsonl`

There are 960 rows from the Banking77 test split, in two buckets: informational intents map to `knowledge` (640) and imperative account requests map to `action` (320; cancel_transfer, terminate_account, edit_personal_details, change_pin, request_refund, lost_or_stolen_card …). These are customer-voice queries, so this measures domain shift for the employee-facing router. The other intents are left out because no defensible mapping exists.

## 5. Where real-derived text enters the bank

- In 21 customer emails in `runs/realism/bank.duckdb`, the body is 2 sentences from one CFPB narrative with the same signal. The anchor sentence must contain the signal keyword, and the next sentence follows it.
- Each email is matched to the customer's actual flag: hardship goes to vulnerable or forbearance, complaint to complaint_open, dispute to dispute, and deceased_notice goes to deceased with the email written by an heir.
- US terms are localised: collector becomes "your collection agency", credit bureau becomes "CRIF / Centrale dei Rischi record", foreclosure becomes "enforcement (pignoramento)", and certified mail becomes PEC.
- Two arrears customers who are **not** flagged also write hardship emails. This is a realistic gap that the signal reader is meant to catch.
- Names, NDGs, IBANs, phones and addresses are fictional (Faker), so PII spans and pseudonyms work exactly as in the demo.

## 6. Still synthetic / limitations

- Every person, company, address and account is generated. The calibration rates marked **Assumption** are not taken from a source.
- The dpd split and the exception shares are judgement calls. RSF and CRIF give default flows, not early-arrears stocks.
- Some CFPB sentences read awkwardly out of context, because only 2 sentences are kept and some contain colloquial or ungrammatical language. That is realistic for customer email, but it is not Italian. A translation pass by the teacher model would be the next step.
- The PII and task sets (`data/pii`, `data/tasks`) are still built from the old generator, and the models were not retrained on this bank.
