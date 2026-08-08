#!/usr/bin/env python3
"""
site-watch — outcome reconciler.

For every alert this employee raised at least RECHECK_H hours ago, go and look at reality
again. Did the problem hold up, or did it fix itself before anyone read the message?

The output is **alert precision**: of the things this employee told a human about, what share
were still true an hour later. Low precision does not mean the model is bad — it means the
GATE is too twitchy. Go tune the thresholds in uptime-check.py.

There is NO model call in this file. This is the part of an AI employee that has nothing to do
with AI, and it is the part that decides whether the employee is worth keeping.
"""
import sys, os
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import lib

EMP = "example-site-watch"
TASK = "reconcile"
RECHECK_H = 1        # don't judge an alert until it has had this long to resolve or persist
BAD_STATUS = 500

rows, due = lib.claims_due(EMP, after_hours=RECHECK_H)
if not due:
    pending = sum(1 for r in rows if r.get("outcome") is None)
    lib.nothing_to_report(EMP, TASK, "0 claims ready to reconcile (%d pending)" % pending)

for claim in due:
    status, elapsed, size, err = lib.http_status(claim["key"])
    if err:
        claim["outcome"] = "still_broken"
    elif status >= BAD_STATUS:
        claim["outcome"] = "still_broken"
    else:
        claim["outcome"] = "self_recovered"
    claim["rechecked_status"] = status

lib.claims_write(EMP, rows)

c = Counter(r["outcome"] for r in due)
held = c["still_broken"]
precision = round(100 * held / len(due)) if due else 0

summary = ("reconciled %d alert(s) after %dh: %d still broken, %d self-recovered. "
           "Alert precision %d%%.%s"
           % (len(due), RECHECK_H, held, c["self_recovered"], precision,
              "  <-- gate is too twitchy; raise the thresholds" if precision < 50 and len(due) >= 3 else ""))

lib.done(EMP, TASK, summary)
