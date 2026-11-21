#!/usr/bin/env python3
"""Minimal ALFRED API client (standard library only).

    export ALFRED_URL=http://127.0.0.1:8080
    export ALFRED_KEY=alf_rm_...            # from runs/.api_keys.json or your operator
    python examples/client.py ask "What is the SME credit limit without committee approval?"
    python examples/client.py brief
    python examples/client.py actions
    python examples/client.py approve A-CASE-0001-1     # asks YOU at the terminal before sending X-Human-Approval

Human approval rule: approve() only sends `X-Human-Approval: true` after a person typed "yes" at the prompt.
If you wrap this in an agent, keep that prompt in front of a human. Agents must never set the header themselves.
"""
import json, os, sys, urllib.error, urllib.request


class AlfredError(Exception):
    def __init__(self, status, code, message):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code = status, code


class Alfred:
    def __init__(self, base=None, key=None):
        self.base = (base or os.environ.get("ALFRED_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.key = key or os.environ["ALFRED_KEY"]

    def _call(self, method, path, body=None, headers=None):
        h = {"X-API-Key": self.key, "Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read()).get("error", {})
            except Exception:
                err = {}
            raise AlfredError(e.code, err.get("code", "http_error"), err.get("message", e.reason)) from None

    def ask(self, question):           return self._call("POST", "/v1/ask", {"question": question})
    def brief(self):                   return self._call("GET", "/v1/brief")
    def pseudonymise(self, text):      return self._call("POST", "/v1/pseudonymise", {"text": text})
    def memory(self, status=None):     return self._call("GET", "/v1/memory" + (f"?status={status}" if status else ""))
    def propose_fact(self, text):      return self._call("POST", "/v1/memory", {"text": text})
    def decide_fact(self, fid, d):     return self._call("POST", f"/v1/memory/{fid}/decision", {"decision": d})
    def run_autopilot(self):           return self._call("POST", "/v1/autopilot/run")
    def cases(self, status=None):      return self._call("GET", "/v1/autopilot/cases" + (f"?status={status}" if status else ""))
    def kpis(self):                    return self._call("GET", "/v1/autopilot/kpis")
    def actions(self, status="proposed"): return self._call("GET", f"/v1/actions?status={status}")
    def audit(self, object_id=None):   return self._call("GET", "/v1/audit" + (f"?object_id={object_id}" if object_id else ""))

    def approve(self, action_id, decision="approved", approver=None):
        """Shows the action to a person and sends X-Human-Approval only if they confirm."""
        a = next((x for x in self.actions("proposed") if x["action_id"] == action_id), None)
        if not a:
            raise AlfredError(404, "not_found", f"{action_id} is not waiting for approval")
        print(json.dumps(a, indent=2, ensure_ascii=False))
        if input(f"{decision.upper()} {action_id}? Type 'yes' to confirm: ").strip().lower() != "yes":
            print("Not sent.")
            return None
        hdr = {"X-Human-Approval": "true"}
        if approver:
            hdr["X-Approved-By"] = approver
        return self._call("POST", f"/v1/actions/{action_id}/decision", {"decision": decision}, hdr)


if __name__ == "__main__":
    c, cmd, args = Alfred(), (sys.argv[1] if len(sys.argv) > 1 else "brief"), sys.argv[2:]
    try:
        out = {"ask": lambda: c.ask(" ".join(args)), "brief": c.brief, "pseudonymise": lambda: c.pseudonymise(" ".join(args)),
               "memory": lambda: c.memory(*args[:1]), "actions": c.actions, "kpis": c.kpis, "cases": lambda: c.cases(*args[:1]),
               "approve": lambda: c.approve(args[0], approver=os.environ.get("USER")),
               "reject": lambda: c.approve(args[0], "rejected", approver=os.environ.get("USER"))}[cmd]()
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except AlfredError as e:
        sys.exit(f"error: {e}")
