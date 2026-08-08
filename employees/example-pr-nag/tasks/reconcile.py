#!/usr/bin/env python3
"""
pr-nag — outcome reconciler. NO MODEL CALL IN THIS FILE.

For every PR this employee nagged about at least RECHECK_H hours ago, go and look: did it merge,
did it close, or is it still sitting there?

The output is the **nag-to-merge rate** — of the things this employee told a human about, how
many actually moved. That number is the only honest answer to "is this employee worth keeping?",
and it is the one thing no agent platform will compute for you, because only you know what
"acted on" means in your world.
"""
import sys, os, json
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import lib

EMP = "example-pr-nag"
TASK = "reconcile"
RECHECK_H = 24   # give a human a working day before judging whether they acted

rows, due = lib.claims_due(EMP, after_hours=RECHECK_H)
if not due:
    pending = sum(1 for r in rows if r.get("outcome") is None)
    lib.nothing_to_report(EMP, TASK, "0 nags ready to reconcile (%d pending)" % pending)

for claim in due:
    repo, _, num = claim["key"].partition("#")
    try:
        out = lib.shell(["gh", "pr", "view", num, "--repo", repo, "--json", "state,mergedAt"])
        st = json.loads(out or "{}")
        state = (st.get("state") or "").upper()
        if state == "MERGED" or st.get("mergedAt"):
            claim["outcome"] = "merged"
        elif state == "CLOSED":
            claim["outcome"] = "closed_unmerged"
        else:
            claim["outcome"] = "still_open"
    except Exception as ex:
        claim["outcome"] = "unknown"
        claim["error"] = str(ex)[:120]

lib.claims_write(EMP, rows)

c = Counter(r["outcome"] for r in due)
moved = c["merged"] + c["closed_unmerged"]
rate = round(100 * moved / len(due)) if due else 0

summary = ("reconciled %d nag(s) after %dh: %d merged, %d closed, %d still open. "
           "Nag-to-merge rate %d%%.%s"
           % (len(due), RECHECK_H, c["merged"], c["closed_unmerged"], c["still_open"], rate,
              "  <-- nobody is acting on this employee; find out why before adding a second one"
              if rate < 30 and len(due) >= 3 else ""))

lib.done(EMP, TASK, summary)
