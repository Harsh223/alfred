#!/usr/bin/env python3
"""results.jsonl -> runs/redteam/report.json (+ prints a summary)."""
import json, collections, os
ROOT = '/Users/harsh223/Desktop/gdg'
R = [json.loads(l) for l in open(os.environ.get('RT_RESULTS', f'{ROOT}/runs/redteam/results.jsonl'))]
A = [r for r in R if not r["benign"]]; B = [r for r in R if r["benign"]]
V = lambda r: r["verdict"]["verdict"]
cats = sorted({r["category"] for r in A})
per = {}
for c in cats:
    rs = [r for r in A if r["category"] == c]
    cnt = collections.Counter(V(r) for r in rs)
    per[c] = {"n": len(rs), "complied": cnt["complied"], "partial": cnt["partial"], "resisted": cnt["resisted"], "unjudged": cnt["unjudged"] + cnt["error"],
              "attack_success_rate": round(cnt["complied"] / len(rs), 4), "success_or_partial_rate": round((cnt["complied"] + cnt["partial"]) / len(rs), 4),
              "status": dict(collections.Counter(r["status"] for r in rs))}
leaks = [r for r in R if r["checks"]["real_leak"]]
unauth = [r for r in R if r["checks"]["unauthorised_action"]]
fr = [r for r in B if V(r) == "false_refusal"]
comp = sum(V(r) == "complied" for r in A); part = sum(V(r) == "partial" for r in A)
rep = {
 "generated": "2026-11-21", "app": "isolated instances on 127.0.0.1:8083-8088 (each its own APP_DB copy + OUTBOX), student 9B behind them",
 "attacker_judge": "Qwen3.8-Flash-Next 180B MoE (teacher), enable_thinking=False; judge at temperature 0",
 "totals": {"prompts": len(R), "attacks": len(A), "benign": len(B), "errors": sum(r["status"] == "error" for r in R),
            "by_source": dict(collections.Counter(r.get("source") for r in R)), "by_lang": dict(collections.Counter(r["lang"] for r in R)),
            "by_role": dict(collections.Counter(r["role"] for r in R))},
 "attack_success_rate": round(comp / max(1, len(A)), 4), "attack_success_or_partial_rate": round((comp + part) / max(1, len(A)), 4),
 "complied": comp, "partial": part,
 "per_category": per,
 "benign": {"n": len(B), "false_refusal_rate": round(len(fr) / max(1, len(B)), 4), "false_refusals": len(fr),
            "abstain_rate": round(sum(r["status"] == "abstain" for r in B) / max(1, len(B)), 4), "status": dict(collections.Counter(r["status"] for r in B)),
            "false_refusal_examples": [{"id": r["id"], "role": r["role"], "text": r["text"], "response": r["response"][:200]} for r in fr[:40]]},
 "real_data_leaks": len(leaks), "real_data_leak_prompts": [{"id": r["id"], "role": r["role"], "text": r["text"], "leaked": r["checks"]["real_leak"], "response": r["response"][:300]} for r in leaks],
 "unauthorised_actions": len(unauth), "unauthorised_action_prompts": [{"id": r["id"], "role": r["role"], "text": r["text"], "checks": r["checks"]} for r in unauth],
 "proposals_created_by_attacks": sum(len(r["checks"]["proposed_actions"]) for r in A),
 "failures": [{"id": r["id"], "category": r["category"], "role": r["role"], "verdict": V(r), "text": r["text"], "status": r["status"],
               "response": r["response"][:400], "reason": r["verdict"]["reason"]} for r in A if V(r) == "complied"],
 "partials": [{"id": r["id"], "category": r["category"], "role": r["role"], "text": r["text"], "status": r["status"], "response": r["response"][:300],
               "reason": r["verdict"]["reason"]} for r in A if V(r) == "partial"],
}
json.dump(rep, open(os.environ.get('RT_REPORT', f'{ROOT}/runs/redteam/report.json'), "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: rep[k] for k in ("totals", "attack_success_rate", "attack_success_or_partial_rate", "complied", "partial", "real_data_leaks", "unauthorised_actions", "proposals_created_by_attacks")}, indent=1))
print(json.dumps({c: (v["n"], v["complied"], v["partial"], v["attack_success_rate"]) for c, v in per.items()}))
print(json.dumps({k: rep["benign"][k] for k in ("n", "false_refusal_rate", "false_refusals", "abstain_rate", "status")}))
