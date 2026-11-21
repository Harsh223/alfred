#!/usr/bin/env python3
"""Guard model: Qwen3.5-0.8B fine-tuned to flag attacks on the assistant (replaces regex-only filtering).
Data: public prompt-injection sets (deepset Apache-2.0, jackhhao Apache-2.0, Lakera gandalf MIT, SPML MIT)
      + our red-team attacks from the 180B attacker (80% train / 20% held out) + benign employee questions.
  train_guard.py build  -> /root/guard/{train,test_ours,test_public}.jsonl  (+ SFT file)
Training/eval reuse train_student.py and run_tasks.py (task 'guard')."""
import json, os, random, sys
from datasets import load_dataset
R = random.Random(3); OUT = "/root/guard"; os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, os.path.dirname(__file__)); from prompts import messages

pub = []
for name, split, tcol, lcol, pos in [("deepset/prompt-injections", "train", "text", "label", 1), ("jackhhao/jailbreak-classification", "train", "prompt", "type", "jailbreak"),
                                     ("Lakera/gandalf_ignore_instructions", "train", "text", None, None), ("reshabhs/SPML_Chatbot_Prompt_Injection", "train", "User Prompt", "Prompt injection", 1)]:
    try:
        ds = load_dataset(name, split=split)
        for r in ds.select(range(min(len(ds), 2500))):
            t = r.get(tcol)
            if not t or len(t) > 1500: continue
            lab = "attack" if lcol is None else ("attack" if r.get(lcol) == pos else "safe")
            pub.append({"text": t, "label": lab, "src": name})
    except Exception as e:
        print("skip", name, e)
R.shuffle(pub); pub_test, pub_train = pub[:400], pub[400:]

ours = [json.loads(l) for l in open("/root/attacks.jsonl")]
R.shuffle(ours); cut = int(len(ours) * .2)
ours = [{"text": a["text"], "label": "safe" if a.get("benign") else "attack", "src": f"redteam:{a.get('category')}"} for a in ours]
ours_test, ours_train = ours[:cut], ours[cut:]
benign = [{"text": q, "label": "safe", "src": "employee"} for q, _ in json.load(open("/root/router_llm_data.json"))]
train = pub_train + ours_train * 2 + benign
R.shuffle(train)
for n, rows in (("train", train), ("test_ours", ours_test), ("test_public", pub_test)):
    with open(f"{OUT}/{n}.jsonl", "w") as f:
        for r in rows: f.write(json.dumps({"task": "guard", "input": {"text": r["text"]}, "gold": {"label": r["label"]}, "kind": r["src"].split(":")[0]}, ensure_ascii=False) + "\n")
with open(f"{OUT}/sft.jsonl", "w") as f:
    for r in train: f.write(json.dumps({"messages": messages("guard", {"text": r["text"]}) + [{"role": "assistant", "content": r["label"].upper()}]}, ensure_ascii=False) + "\n")
print({"train": len(train), "test_ours": len(ours_test), "test_public": len(pub_test), "public_total": len(pub)})
