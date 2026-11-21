"""Re-judge rows whose judge call failed (unjudged)."""
import json, sys, os, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
import judge
P = '/Users/harsh223/Desktop/gdg/runs/redteam/results.jsonl'
R = [json.loads(l) for l in open(P)]
todo = [r for r in R if r["verdict"]["verdict"] == "unjudged"]
def f(r):
    v = judge.score(r)
    r["verdict"] = v
with cf.ThreadPoolExecutor(16) as ex: list(ex.map(f, todo))
with open(P, "w") as fo:
    for r in R: fo.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(todo), sum(r["verdict"]["verdict"] == "unjudged" for r in R))
