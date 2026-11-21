#!/usr/bin/env python3
"""Question router: a tiny neural classifier trained FROM SCRATCH (random init, no pretrained weights).

Architecture: hashed word + char-3/4/5-gram EmbeddingBag (2^16 x 48) -> linear (fastText-style), ~3.1M params, <1 ms on CPU.
Intents:
  knowledge       policy / procedure / document question  -> retrieval + assistant
  my_work         "what's on my plate", "status of my work" -> live approvals, exceptions, tickets, brief
  customer        question about a specific customer/loan   -> retrieval + vault (role-gated)
  action          "send a reminder to…", "approve all…"     -> PROPOSE an action, never execute
  help            greetings, "what can you do"              -> capability card
  out_of_scope    weather, football, poems, crypto prices   -> polite decline

  python brain/router.py train   -> runs/router.pt + runs/router_eval.json
"""
import json, os, random, re, sys, time, zlib
import torch, torch.nn as nn

ROOT = os.path.join(os.path.dirname(__file__), "..")
INTENTS = ["knowledge", "my_work", "customer", "action", "help", "out_of_scope"]
B, D = 1 << 16, 48


def feats(text):
    t = text.lower().strip()
    toks = re.findall(r"<[a-z]+_\d+>|[\wà-ÿ']+|[?!]", t)
    toks = ["<PSEUDO>" if x.startswith("<") else x for x in toks]
    out = [f"w:{w}" for w in toks] + [f"b:{a}_{b}" for a, b in zip(toks, toks[1:])]
    s = f" {t} "
    out += [f"c{n}:{s[i:i+n]}" for n in (3, 4, 5) for i in range(len(s) - n + 1)]
    return [zlib.crc32(f.encode()) % B for f in out] or [0]


class Router(nn.Module):
    def __init__(self):
        super().__init__(); self.emb = nn.EmbeddingBag(B, D, mode="mean"); self.out = nn.Linear(D, len(INTENTS))
    def forward(self, ids, offsets): return self.out(self.emb(ids, offsets))


def batchify(texts):
    ids, offs = [], []
    for t in texts:
        offs.append(len(ids)); ids += feats(t)
    return torch.tensor(ids), torch.tensor(offs)


_M = None
def predict(text):
    global _M
    if _M is None:
        _M = Router(); _M.load_state_dict(torch.load(f"{ROOT}/runs/router.pt", map_location="cpu")); _M.eval()
    with torch.no_grad():
        p = torch.softmax(_M(*batchify([text])), -1)[0]
    i = int(p.argmax()); return INTENTS[i], float(p[i])


# ------------------------------------------------------------------ synthetic training data (templated, EN + IT, typos)
R = random.Random(5)
POLICY_TOPICS = ["SME credit limit", "credit line without committee", "mortgage instalment to income ratio", "late fee for PEC reminder", "KYC renewal for high risk",
                 "nightly batch runbook", "Q3 supervisory report deadline", "branch opening hours", "Confidi guarantee coverage", "reminder procedure after 60 days",
                 "what happens after 90 days past due", "due diligence period", "disk full on db-core-03", "RICONC-02 job", "covenant review deadline", "AML alert procedure"]
T = {
 "knowledge": ["what is the {p}?", "whats the {p}", "how does the {p} work", "tell me the rule for {p}", "where can I find the {p}", "explain the {p}",
               "qual è il {p}?", "{p}?", "do we have a policy on {p}", "remind me about the {p}", "why did the nightly batch fail?", "which job do I re-run if the batch fails",
               "when is the {p} due", "what does the procedure say about {p}", "is there a limit on {p}", "what changed in credit policy v3"],
 "my_work": ["what's the status of my work?", "whats status of my work", "what's on my plate today", "what do I need to do today?", "any approvals waiting for me?",
             "what needs my attention", "summarise my day", "give me my to-do list", "what's pending for me", "am I behind on anything?", "what should I focus on this morning",
             "cosa devo fare oggi?", "ho qualcosa in sospeso?", "status update please", "what's left on my desk", "show me my open items", "anything urgent for me?",
             "how many cases need my review", "what are my tasks", "catch me up", "what did I miss", "where am I with my work", "my workload?", "what's my queue looking like"],
 "customer": ["tell me about {c}", "what does {c} owe?", "is {c} behind on payments", "status of loan {l}", "who is the RM for {c}", "has {c} paid yet",
              "why was {c} flagged", "any complaints from {c}?", "what's the exposure on {c}", "which company is breaching its covenant?", "chi è {c}?",
              "show me {c}'s loans", "did {c} send the documents", "what's going on with {l}", "which customers have expiring KYC documents"],
 "action": ["send a reminder to {c}", "email {c} about the missing payment", "approve all pending reminders", "escalate {l} to legal", "post the late fee on {l}",
            "draft a letter to {c}", "call {c} tomorrow", "schedule a follow-up with {c}", "manda un sollecito a {c}", "approve the reminder for {c}",
            "reject the escalation for {l}", "send the PEC now", "write an email to the customer", "renew the KYC for {c}", "block the card of {c}"],
 "help": ["hi", "hello", "hey there", "good morning", "thanks!", "thank you", "what can you do?", "how do I use this?", "help", "who are you?", "ciao",
          "buongiorno", "what are you able to answer", "how does this work", "can you help me", "grazie mille", "ok", "cool"],
 "out_of_scope": ["what's the weather in Turin?", "who won the Juventus game", "write me a poem", "what's the bitcoin price", "tell me a joke", "best pizza near me",
                  "translate this to Chinese", "what's the capital of Peru", "book me a flight to London", "che tempo fa domani?", "recommend a movie",
                  "how tall is the Eiffel tower", "play some music", "what's 17 times 23"],
}
def typo(s):
    if R.random() < .25 and len(s) > 6:
        i = R.randrange(1, len(s) - 1); s = s[:i] + s[i + 1:] if R.random() < .5 else s[:i] + s[i] + s[i:]
    if R.random() < .3: s = s.lower().rstrip("?")
    return s
def fill(t):
    return t.replace("{p}", R.choice(POLICY_TOPICS)).replace("{c}", R.choice([f"<CLIENT_{R.randint(1,400):04d}>", "Mario Rossi", "Ivo Bonomo", "the customer", "Bianchi srl"])) \
            .replace("{l}", R.choice([f"<LOAN_{R.randint(1,500):04d}>", "MUT-2024-00042", "FID-2024-00002", "the loan"]))

# Hand-written held-out test (never templated): realistic human phrasings, incl. the user's own.
HUMAN_TEST = [
 ("whats status of my work?", "my_work"), ("what's the status of my work", "my_work"), ("so what's waiting for me", "my_work"), ("anything I should look at first?", "my_work"),
 ("did anything blow up overnight that's on me", "my_work"), ("what's my day like", "my_work"), ("do I have stuff to approve", "my_work"), ("quick summary of what I owe today", "my_work"),
 ("cosa ho da fare stamattina?", "my_work"), ("where do things stand for me", "my_work"),
 ("why did the nightly batch fail?", "knowledge"), ("how much can we lend an SME without committee", "knowledge"), ("whats the late fee on a pec", "knowledge"),
 ("rules for kyc refresh high risk?", "knowledge"), ("when's the bank of italy report due", "knowledge"), ("what does the runbook say about disk full", "knowledge"),
 ("max rata reddito mutui?", "knowledge"), ("what's the reminders procedure", "knowledge"),
 ("which company is breaching its covenant?", "customer"), ("is Ivo Bonomo in trouble", "customer"), ("has <CLIENT_0042> paid", "customer"), ("tell me about the AML alert customer", "customer"),
 ("what's happening with FID-2024-00002", "customer"), ("who has expiring ID documents", "customer"),
 ("send Mario Rossi a reminder", "action"), ("approve everything that's safe", "action"), ("escalate the 90+ cases", "action"), ("email the covenant customer for a meeting", "action"),
 ("go ahead and send the PECs", "action"),
 ("hey", "help"), ("what can you help me with", "help"), ("thanks that's great", "help"), ("how do I approve things here?", "help"),
 ("what's the weather like", "out_of_scope"), ("who's playing tonight", "out_of_scope"), ("write a haiku about banks", "out_of_scope"), ("price of gold today?", "out_of_scope"),
]


def train():
    rows = []
    for intent, temps in T.items():
        keep = temps[:-2]                         # last 2 templates of each intent held out
        for _ in range(900): rows.append((typo(fill(R.choice(keep))), intent))
    held = [(typo(fill(t)), i) for i, temps in T.items() for t in temps[-2:] for _ in range(20)]
    llm = f"{ROOT}/runs/router_llm_data.json"
    if os.path.exists(llm):   # questions written by our distilled 9B assistant (data distillation); 15% kept aside as a third test set
        L = [tuple(x) for x in json.load(open(llm))]; R.shuffle(L); cut = int(len(L) * .15)
        llm_test, rows = L[:cut], rows + L[cut:] * 3
    else: llm_test = []
    R.shuffle(rows)
    m = Router(); opt = torch.optim.Adam(m.parameters(), lr=0.02); lossf = nn.CrossEntropyLoss(); t0 = time.time()
    for ep in range(8):
        for i in range(0, len(rows), 64):
            b = rows[i:i + 64]; ids, offs = batchify([x for x, _ in b]); y = torch.tensor([INTENTS.index(l) for _, l in b])
            opt.zero_grad(); loss = lossf(m(ids, offs), y); loss.backward(); opt.step()
    m.eval(); torch.save(m.state_dict(), f"{ROOT}/runs/router.pt")
    global _M; _M = m
    def acc(data): return round(sum(predict(x)[0] == y for x, y in data) / len(data), 4)
    t1 = time.time(); [predict(x) for x, _ in HUMAN_TEST]; ms = (time.time() - t1) * 1000 / len(HUMAN_TEST)
    errs = [(x, y, predict(x)[0]) for x, y in HUMAN_TEST if predict(x)[0] != y]
    res = {"params": sum(p.numel() for p in m.parameters()), "train_rows": len(rows), "train_seconds": round(t1 - t0, 1),
           "acc_heldout_templates": acc(held), "acc_heldout_llm_written": acc(llm_test) if llm_test else None, "acc_human_written": acc(HUMAN_TEST), "n_human": len(HUMAN_TEST), "ms_per_query_cpu": round(ms, 2), "errors": errs}
    json.dump(res, open(f"{ROOT}/runs/router_eval.json", "w"), indent=1); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "train": train()
    else: print(predict(" ".join(sys.argv[1:])))
