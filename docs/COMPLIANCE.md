# Lumen Bank: regulatory compliance map

Status as of **21 Nov 2026**. Scope: the prototype in `docs/SYSTEM.md` and `docs/SPEC.md` (fictional Turin bank, synthetic data only). This is an engineering map, not legal advice. Sources are cited as [Sn] (list at the end). **UNVERIFIED** means we could not confirm the point against a primary source.

**Our framing.** In production the bank would be both the **provider** of these AI systems (it builds them and puts them into service under its own name, AI Act Art 3(3)) and their **deployer** (Art 3(4)) [S11]. The **hackathon** build differs from production: it ran on rented, self-hosted GPU servers in place of the bank's on-prem hardware, and the app called the student model over an authenticated HTTPS endpoint. Only synthetic data was used.

Two things in the prototype do not yet match the target design: the `vault` table is **plaintext** in DuckDB, and login is a **cookie role with no authentication** (`/as/{role}`). Both are listed as gaps below.

---

## 1. GDPR (Reg. 2016/679) [S1]

| Requirement | How we meet it (feature) | Evidence / where | Gap / next step |
|---|---|---|---|
| Art 5(1)(c) data minimisation | The pseudonymiser runs before any LLM call. The LLM and app read only the `*_anon` tables. Real values exist only in `raw_*` tables and the `vault`. | `anonymizer/pii.py`, `docs/SPEC.md`; 0 leaked values out of 430 on the live workspace (`runs/metrics.md`) | Recall on unfamiliar formats is 93%, not 100%. Add a second detector as a safety net and sample leaked spans in production. Add a `HEALTH` label (see Art 9). |
| Art 5(1)(b) purpose limitation | The department filter runs before search. Collections data is used only for arrears handling. The Brain answers only from approved memory. | `brain/core.py` `ROLES`, access-denied audit events | Write a purpose register for each data flow. Bar reuse of collections or Brain data for marketing or credit scoring. |
| Art 5(1)(e) storage limitation | – | – | **Gap:** there is no retention schedule for the vault, memory facts, audit logs or the outbox. Retention must be reconciled with banking record-keeping duties (exact periods UNVERIFIED; legal to confirm). |
| Art 6 lawful basis: collections | Art 6(1)(b), performance of the loan contract (reminders, contractual late fee). Art 6(1)(c), legal obligation, where law requires steps such as forbearance (CCD2 Art 35). | Autopilot rules in `docs/SPEC.md` | Record the basis in the RoPA. Escalation to legal can also rest on Art 6(1)(f) (pursuing legal claims). |
| Art 6 lawful basis: Company Brain | Art 6(1)(f), legitimate interest in internal knowledge management. Customer data stays pseudonymised. Re-identification is role-gated. | `brain/core.py` (`reid` flag per role) | **Gap:** no legitimate-interest assessment yet. Employee prompts and security logs are employee data, so Italian Art 4 L.300/1970 (remote monitoring) [S30] needs a labour-law review. |
| Art 22 automated decisions | Every irreversible, customer-affecting action waits for an identified human approver: `send_reminder`, `post_late_fee`, `escalate`. Exceptions stop for a person. Reminder letters are deterministic templates, not LLM text. | `autopilot/engine.py` (`letter()`, exceptions), `/actions`, `audit` table | Human review must be meaningful, not rubber-stamping [S2]. Log time-to-approve and override rate. Forbid one-click bulk approval of fees and escalations. CJEU *SCHUFA* C-634/21: a score a decision-maker "draws strongly on" can itself be an Art 22 decision [S6]. So keep the triage output advisory. |
| Art 15(1)(h) / Art 22(3) explanation | Each case stores the rule, decision, reason and model output as JSON. | `cases.reason`, `audit.detail` | Write a customer-facing explanation template. *Dun & Bradstreet* C-203/22: the explanation must cover "the procedure and principles actually applied" [S7]. |
| Art 25 data protection by design | Pseudonymisation is the core design choice (Art 4(5): the additional information is kept separately). Consistent tokens. Inference is local, with no third-party AI API. Actions are only proposed. | `docs/SYSTEM.md` pipeline | Pseudonymised data **is still personal data** for the bank, which holds the key (Recital 26) [S1]; EDPB Guidelines 01/2025 [S4]. *EDPS v SRB* C-413/23 P (4 Sep 2025) assesses this from the recipient's side [S5], but it does not help us: the key holder and the LLM are inside the same controller. |
| Art 30 records of processing | – | – | **Gap:** no RoPA. It can be generated from the `docs/SPEC.md` tables and roles. |
| Art 32 security | Role from login only, never from chat text. Department filter before retrieval. Every re-identification is audited (`re_identification` event). Prompt-injection detection with security log. Local models. | `brain/core.py` (`INJECTION_RE`, `audit()`), `/audit` | **Gaps:** (1) the vault is plaintext; it needs encryption with KMS/HSM keys held apart from the data; (2) there is no authentication; it needs SSO and MFA; (3) injection defence is a regex and needs a classifier plus red-team suite; (4) DuckDB is a single file with no access control. |
| Art 33/34 breach notification | Audit trail gives the forensic timeline. | `audit` table | A PII leak through the model counts as a personal-data breach (72 h to the Garante). Link it to the DORA incident runbook (§3). |
| Art 35 DPIA | – | – | **DPIA required.** Several WP248 criteria are met: evaluation, automated decisions with legal effect, sensitive data, vulnerable data subjects, innovative technology [S3]. The Garante's list covers large-scale scoring and profiling [S8]. |
| Data subject rights (Arts 15–21) | The vault maps each person to one pseudonym, so every record about them can be found. | `vault`, `memory`, `actions` tables | **Gap:** no DSAR or erasure tooling. Erasure must propagate to vault, memory and outbox, but not to legally retained records. Art 21 objection applies to the Brain's legitimate-interest processing. |
| Art 9 special categories (health in hardship emails) | The signal reader outputs only a flag (hardship, death, complaint, dispute) and sends the case to a human. It never auto-actions. | `runs/router*.json`, autopilot exceptions | **Gap, legally open:** no Art 9(2) condition is identified yet for health details in customer emails. Next steps: (1) add a `HEALTH` span label so diagnoses are masked before the LLM; (2) keep only the flag; (3) settle the Art 9(2) basis in the DPIA. GDPR does not cover deceased persons (Recital 27), but Italian law adds protections (Codice privacy art. 2-terdecies, UNVERIFIED wording). |
| Training data | Only synthetic data and Apache-2.0 public data (Gretel). No real personal data reached any model. | `docs/SYSTEM.md` §Data | Fine-tuning on real bank documents later would need its own basis and DPIA (EDPB Opinion 28/2024 on AI models) [S10]. |

**GDPR changes in the pipeline.** The Commission proposed a "Digital Omnibus" (Nov 2025) that would amend GDPR, including the definition of personal data and pseudonymised data. Secondary sources report a Council mandate in Oct 2026, with Parliament's position pending. **Nothing is adopted; current GDPR applies.** The Council-mandate details are UNVERIFIED against the Council register.

---

## 2. EU AI Act (Reg. 2024/1689 as amended by Reg. 2026/1744, the "Digital Omnibus on AI")

### 2a. Timeline (verified against EUR-Lex [S11][S12])

| Date | What applies |
|---|---|
| 1 Aug 2024 | Entry into force |
| 2 Feb 2025 | Ch. I–II: Art 4 AI literacy, Art 5 prohibitions |
| 2 Aug 2025 | GPAI model obligations (Ch. V), governance, penalties |
| 2 Aug 2026 | General application, including **Art 50 transparency** |
| 27 Jul 2026 | Reg. **2026/1744** in force (signed 8 Jul 2026, OJ 24 Jul 2026). Softened **Art 4**: "take measures to support the development of AI literacy… does not require… any specific level". New Art 4a (special-category data for bias detection) |
| 2 Dec 2026 | Art 50(2) machine-readable marking for generative systems placed on the market **before** 2 Aug 2026. New Art 5 bans (nudification/CSAM) |
| **2 Dec 2027** | High-risk obligations (Ch. III Sections 1–3, Arts 6–27) for **Annex III** systems. Previously 2 Aug 2026 |
| 2 Aug 2028 | Same for Annex I (product-embedded) systems |

### 2b. Risk classification per component

Annex III point 5(b) is high-risk: "AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score", except fraud detection [S11]. Under Art 6(3), an Annex III system can escape high-risk status if it only performs a narrow or preparatory task. That escape is **not available if the system profiles natural persons**.

| Component | Our classification | Reasoning | What would flip it to high-risk |
|---|---|---|---|
| Overdue-loan triage (rules + 9B cross-check) | **Not Annex III 5(b)**. Minimal risk, but documented and built to high-risk-style controls. | (1) It does not assess ability to repay or produce a score. (2) It maps days past due, amount and flags to the bank's written policy. (3) The LLM only cross-checks a deterministic rule. (4) Every exception and every irreversible step goes to a human. (5) Recital 58 ties 5(b) to *access* to credit; this system works after the loan is granted. SME loans to legal persons fall outside "natural persons", but sole traders do not. | Adding propensity-to-pay or "cure" scores. Using the output in forbearance or restructuring eligibility, or in new credit decisions (CCD2 Art 18 reassessment). Because triage arguably involves profiling (economic situation), Art 6(3) cannot be relied on as a fallback. If the scope drifts, treat it as high-risk. |
| Company Brain (employee assistant) | Minimal risk. Art 50(1) applies: users are told they are dealing with an AI. | It is a Q&A and briefing tool over approved documents and only proposes actions. It is not a credit decision tool. | Using it to recommend granting or refusing credit to individuals. Under Art 25(1)(c), changing a system's intended purpose so it becomes high-risk makes the bank a high-risk provider. Using its security or usage logs to evaluate staff performance would fall under Annex III 4(b), workers. **Intended-purpose statement and in-product guardrail needed.** |
| Signal reader (0.8B) | Minimal risk | It classifies text to route cases to humans. It is not emotion recognition, which is defined on *biometric* data (Art 3(39)), so Art 5(1)(f) and Annex III 1(c) do not apply. | Feeding its flags into creditworthiness or pricing decisions |
| PII pseudonymiser, router | Minimal risk | These are privacy and routing utilities that make no decisions about people. | – |

**Art 5 prohibited practices:** none apply. There is no social scoring, no manipulation and no biometric processing. Vulnerability is used to *protect* (stop for a human), never to exploit (Art 5(1)(b)).

### 2c. Obligations

| Requirement | How we meet it | Evidence / where | Gap / next step |
|---|---|---|---|
| Art 4 AI literacy (since 2 Feb 2025; softened 27 Jul 2026) | The UI labels assumptions. Approvers see the rule, the model output and any disagreement. | `/autopilot`, `/actions` | Run a training module for approvers and curators and keep attendance records. |
| Art 50(1) interaction disclosure | The Brain is clearly presented as an AI assistant. | `app/ui.py` | Add an explicit "AI-generated" label on every answer and brief. |
| Art 50(2) marking of synthetic text (applies now to new systems) | Customer reminder letters are templates, not generated, so out of scope. | `autopilot/engine.py` `letter()` | **Gap:** Brain `draft_email` proposals are LLM text. Either add machine-readable marking or document why the "assistive/standard editing" exemption applies. |
| Art 26 deployer duties; Art 12 logging; Art 14 human oversight (only if high-risk; from 2 Dec 2027) | Done voluntarily: full audit trail, human approval gates, "I don't know" abstention, fallback to rules-only. | `audit` table, `/audit`, `tests/jury_checks.py` | Keep logs for at least 6 months (Art 26(6) benchmark). Note that Art 27 FRIA is mandatory for 5(b) deployers if we are ever reclassified. |
| Art 6(4) documentation of "not high-risk" | – | – | **Gap:** write a classification memo. Required if we rely on Art 6(3). Recommended regardless. |
| GPAI (Art 53) | Obligations sit with the Qwen model provider. Our LoRA (8.5 min, 1 GPU) is far below the Commission's one-third-of-original-compute threshold for becoming a GPAI provider [S13]. | `llm/train_student.py` | Confirm model licences (Qwen variants and GLiNER: UNVERIFIED for the exact checkpoints named in SYSTEM.md). |
| Italy: Law 132/2025 on AI (in force 10 Oct 2025) [S14] | – | – | Review employer duties to inform workers and the national authority set-up for financial supervision (UNVERIFIED details). |

---

## 3. DORA (Reg. 2022/2554, applies since 17 Jan 2025) [S15]

| Requirement | How we meet it | Evidence / where | Gap / next step |
|---|---|---|---|
| Arts 5–6, 8 ICT risk framework, asset identification | All models run on bank-controlled infrastructure in production. Components are clearly separated (pseudonymiser, vault, LLM, app). | `docs/SYSTEM.md` architecture | Add the GPU servers, model weights, vault and DuckDB to the ICT asset inventory and risk register, and name an owner for each. |
| Art 9 protection; RTS 2024/1774 Arts 6–7 encryption and key management [S16] | Role gating. No outbound AI API calls in production. | `brain/core.py` | **Gap:** vault encryption, authentication and secrets handling. `STUDENT_TOKEN` currently sits in an env file. |
| Art 10 detection; RTS 2024/1774 Art 12 logging | Security events are logged (`security_injection_attempt`, `injection_flagged`, `access_denied`). | `audit` table | Forward the logs to the SOC/SIEM. Make the audit table tamper-evident (append-only or hashed). |
| Arts 11–12 response, recovery, backup | Fallback chain student → teacher → offline stub. The deterministic autopilot rules work without the LLM. | `brain/llm.py` | Define RTO/RPO. Back up the vault and test restores. Run a documented degraded-mode procedure. |
| Arts 17–19 incident management, classification, reporting; RTS 2024/1772 [S17], RTS 2025/301 [S18] | Audit trail supports root-cause analysis. | `/audit` | Write a runbook for model incidents (PII leak, wrong action proposed, injection success). Classify them under 2024/1772. Major incidents need an initial notice within 4 h of classification and within 24 h of awareness, an intermediate report within 72 h and a final report within 1 month. File with Bank of Italy or the ECB as applicable. |
| Arts 24–27 resilience testing | Held-out evals, jury checks, human battery, red-team injection email EML-0085. | `tests/`, `runs/metrics.md` | Add the evals to CI before every model or prompt change. TLPT (Art 26) applies only if the bank is designated. |
| Arts 28–30 ICT third-party risk; register of information (Art 28(3), ITS 2024/2956 [S19]) | **Hackathon:** rented self-hosted GPU servers in place of the bank's on-prem hardware, and Hugging Face downloads, synthetic data only. **Production:** on-prem, open weights, no AI API provider. | `docs/SYSTEM.md` | Keep rented hardware out of any production path. Record hardware, support and vLLM vendors in the register. Treat open-weight checkpoints as supply chain: pin hashes, use safetensors, keep an internal mirror. Whether a one-off weight download is an "ICT service" under DORA is our interpretation (UNVERIFIED). |

---

## 4. Banking and consumer rules

| Requirement | How we meet it | Evidence / where | Gap / next step |
|---|---|---|---|
| **CCD2, Dir. 2023/2225: applies from 20 Nov 2026** (Art 48; transposition deadline 20 Nov 2025) [S20]. Italy transposed it with D.Lgs. 31 Dec 2025 n. 212 [S21]. No EU-level postponement found. | – | – | Took effect yesterday. Per secondary sources, existing agreements generally stay under the old regime (Art 47 transitional; UNVERIFIED wording). Check product scope against the new €100k ceiling (reported, secondary). |
| CCD2 Art 35: "reasonable forbearance" before enforcement; default charges no higher than costs, with caps [S20] | Forbearance, hardship and dispute flags stop the autopilot. Escalation to legal always needs a human. | `autopilot/engine.py` exceptions | **Gap:** (1) the flat €15 late fee needs a cost justification under Art 35 and the Italian implementing rules; (2) letters should mention forbearance and the right to discuss; (3) record that forbearance was considered before escalation. |
| CCD2 Art 36: debt advisory services; Art 18(8): human intervention in automated creditworthiness assessment | Signals of hardship are routed to a human. | – | Add a referral to debt advice in hardship workflows. Art 18(8) is not triggered unless a creditworthiness assessment is automated. |
| EBA/GL/2020/06 loan origination and monitoring (applies 30 Jun 2021) [S22] | Signal reader and arrears buckets act as early-warning inputs (Section 8.5, EWI and watch lists). | `cases` buckets | If the LLM ever supports credit decisions, Section 4.3.4 (models for creditworthiness and decision-making) applies: explainability, validation, human override. |
| EBA/GL/2018/06 non-performing and forborne exposures [S23]; EBA/GL/2015/12 arrears and foreclosure (mortgages; amended by GL/2024/10) [S24] | Forbearance flag. Exceptions go to human workout. 90+ days goes to legal only with approval. | `docs/SPEC.md` rules | Align buckets with the bank's NPE and forbearance identification policy. For `mutuo` products, apply the arrears GL (early engagement, staff training, documentation). |
| Bank of Italy, *Trasparenza delle operazioni e dei servizi bancari e finanziari. Correttezza delle relazioni tra intermediari e clienti* [S26] | Plain-language template letters. The complaint flag stops the autopilot. | `autopilot/engine.py` | Compliance must review letter content. Track complaint deadlines and the ABF route. 2025–26 amendments are not reviewed here (UNVERIFIED). |
| Fair collection: Garante general provision on debt collection, 30 Nov 2005 (doc. web 1213644) [S9] | Letters go only to the customer's own channel. No disclosure to third parties. Fixed templates. | outbox (`runs/outbox`) | Check contact frequency, time-of-day rules and limits on pre-recorded calls in the Garante provision. If collections is outsourced, credit-servicer rules apply (D.Lgs. 116/2024, Dir. 2021/2167; not in current scope). |
| EBA/GL/2019/02 outsourcing [S25] | Not relevant to ICT (DORA governs). Relevant only if collections or legal work is outsourced. | – | The EBA consulted (Jul–Oct 2025) on replacement non-ICT third-party guidelines. Final status UNVERIFIED. |
| AML tipping-off: Dir. 2015/849 Art 39 [S27]; D.Lgs. 231/2007 art. 39 [S29]; AMLR 2024/1624 Art 73 from 10 Jul 2027 [S28] | The AML alert appears only to credit and compliance roles, never to IT. The Brain only proposes and never contacts customers. | `brain/core.py` brief (AML events) | **Gap:** (1) `rm_credit` can see compliance documents and the AML alert in the morning brief; restrict AML and SAR items to `compliance` on a need-to-know basis; (2) add an `aml_hold` autopilot exception; (3) block Brain `draft_email` proposals for customers with an open alert; (4) never mention AML in customer text. |

---

## 5. What we tell the jury in 30 seconds

"No customer data reaches a model until our own fine-tuned pseudonymiser has masked it, and that is still personal data, so we treat it as such. Every model is open-weight and runs on the bank's own servers in production. The autopilot never sends a letter, posts a fee or escalates without a named human approving it. Deceased, vulnerable, forbearance, complaint, dispute, unmatched-payment and over-€5k cases always stop for a person, and every step is audited. That keeps us outside GDPR Art 22 'solely automated' decisions. We classify the triage as outside the AI Act's credit-scoring high-risk category because it doesn't score anyone, and we say exactly what would change that. High-risk obligations now start in December 2027 under the Digital Omnibus, but we already log and gate as if they applied. Before production we still need a DPIA, an encrypted vault with real authentication, AML need-to-know controls, CCD2-compliant fees and letters, and DORA runbooks."

## 6. Top 5 gaps before production

1. **Security baseline** (GDPR Art 32, DORA Art 9, RTS 2024/1774). Encrypt the vault with separately held keys. Replace cookie-role login with SSO and MFA. Make the audit log tamper-evident. Replace regex injection detection with a tested classifier.
2. **GDPR paperwork and Art 9.** DPIA, RoPA and legitimate-interest assessment. Retention schedule. DSAR and erasure tooling. A `HEALTH` mask and a settled Art 9(2) basis for health data in hardship emails. Labour-law review (Art 4 L.300/1970) of Brain logging.
3. **AML tipping-off.** Restrict AML items to compliance. Add an AML hold exception to the autopilot. Block customer drafts while an alert is open.
4. **CCD2 (in force since 20 Nov 2026) and fair collection.** Cost-based default charges. Mention forbearance and debt advice in letters. Evidence that forbearance was considered before escalation. Measure approval quality so it is not rubber-stamping.
5. **AI Act and DORA governance.** Art 6 classification memo and intended-purpose guardrails (no credit decisions via the Brain). Decide on Art 50(2) marking for LLM drafts. AI literacy records. ICT register of information, model-incident runbook with DORA and GDPR clocks, RTO/RPO and restore tests. Keep rented hardware out of any production path.

---

## Sources

- [S1] GDPR, Reg. (EU) 2016/679: https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- [S2] WP29/EDPB, Guidelines on automated decision-making and profiling (WP251rev.01): https://ec.europa.eu/newsroom/article29/items/612053
- [S3] WP29/EDPB, DPIA Guidelines (WP248rev.01): https://ec.europa.eu/newsroom/article29/items/611236
- [S4] EDPB, Guidelines 01/2025 on Pseudonymisation (adopted for consultation Jan 2025; final version UNVERIFIED): https://www.edpb.europa.eu/our-work-tools/documents/public-consultations/2025/guidelines-012025-pseudonymisation_en
- [S5] CJEU C-413/23 P, *EDPS v SRB*, 4 Sep 2025: https://curia.europa.eu/juris/liste.jsf?num=C-413/23
- [S6] CJEU C-634/21, *SCHUFA (Scoring)*, 7 Dec 2023: https://curia.europa.eu/juris/liste.jsf?num=C-634/21
- [S7] CJEU C-203/22, *Dun & Bradstreet Austria*, 27 Feb 2025: https://curia.europa.eu/juris/liste.jsf?num=C-203/22
- [S8] Garante, DPIA list, provv. n. 467 of 11 Oct 2018: https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/9058979
- [S9] Garante, debt collection general provision, 30 Nov 2005: https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/1213644
- [S10] EDPB, Opinion 28/2024 on AI models: https://www.edpb.europa.eu/our-work-tools/our-documents/opinion-board-art-64/opinion-282024-certain-data-protection-aspects_en
- [S11] AI Act, Reg. (EU) 2024/1689: https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng
- [S12] Digital Omnibus on AI, Reg. (EU) 2026/1744 (OJ L 24.7.2026; Art 1 points (5), (39), (40)): https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng
- [S13] European Commission, Guidelines for GPAI providers (Jul 2025): https://digital-strategy.ec.europa.eu/en/policies/guidelines-gpai-providers
- [S14] Legge 23 settembre 2025 n. 132 (Italian AI law): https://www.normattiva.it/eli/id/2025/09/25/25G00143/CONSOLIDATED
- [S15] DORA, Reg. (EU) 2022/2554: https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng
- [S16] RTS on ICT risk management framework, Del. Reg. (EU) 2024/1774: https://eur-lex.europa.eu/eli/reg_del/2024/1774/oj/eng
- [S17] RTS on incident classification, Del. Reg. (EU) 2024/1772: https://eur-lex.europa.eu/eli/reg_del/2024/1772/oj/eng
- [S18] RTS on incident reporting, Del. Reg. (EU) 2025/301: https://eur-lex.europa.eu/eli/reg_del/2025/301/oj/eng
- [S19] ITS on register of information, Impl. Reg. (EU) 2024/2956: https://eur-lex.europa.eu/eli/reg_impl/2024/2956/oj/eng
- [S20] Consumer Credit Directive, Dir. (EU) 2023/2225: https://eur-lex.europa.eu/eli/dir/2023/2225/oj/eng
- [S21] D.Lgs. 31 dicembre 2025 n. 212 (CCD2 transposition): https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2025-12-31;212
- [S22] EBA/GL/2020/06, loan origination and monitoring: https://www.eba.europa.eu/regulation-and-policy/credit-risk/guidelines-on-loan-origination-and-monitoring
- [S23] EBA/GL/2018/06, management of non-performing and forborne exposures: https://www.eba.europa.eu/regulation-and-policy/credit-risk/guidelines-on-management-of-non-performing-and-forborne-exposures
- [S24] EBA/GL/2015/12, arrears and foreclosure: https://www.eba.europa.eu/regulation-and-policy/consumer-protection-and-financial-innovation/guidelines-on-arrears-and-foreclosure
- [S25] EBA/GL/2019/02, outsourcing: https://www.eba.europa.eu/regulation-and-policy/internal-governance/guidelines-on-outsourcing-arrangements
- [S26] Banca d'Italia, transparency and fairness provisions: https://www.bancaditalia.it/compiti/vigilanza/normativa/archivio-norme/disposizioni/trasparenza_operazioni/index.html
- [S27] AMLD, Dir. (EU) 2015/849: https://eur-lex.europa.eu/eli/dir/2015/849/oj/eng
- [S28] AMLR, Reg. (EU) 2024/1624 (applies 10 Jul 2027): https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng
- [S29] D.Lgs. 21 novembre 2007 n. 231: https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2007-11-21;231
- [S30] L. 20 maggio 1970 n. 300, art. 4: https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1970-05-20;300~art4

Primary-text checks: the AI Act Omnibus dates and Art 4 wording, the CCD2 Art 18(8), 35 and 48 dates, the DORA article titles, the 2025/301 reporting time limits and the 2024/1774 Art 12 heading were all read in the EUR-Lex text. Other points (CJEU holdings, EBA dates, Italian transposition details, Council GDPR-omnibus mandate) were confirmed through official listings or reputable secondary sources, as marked.
