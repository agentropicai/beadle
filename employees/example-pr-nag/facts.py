"""
Ground truth for pr-nag, checked live at consolidation time.

`lib.consolidate()` calls `facts()` here automatically and tells the model these override
anything in memory.md that contradicts them. This is the fix for the failure where an employee
that watches a number slowly starts remembering the number instead of checking it: memory says
"8 PRs awaiting merge" for weeks after six of them merged, and every digest built on that memory
inherits the lie.

Two rules, both learned the hard way:

  1. **Phrase a fact as an instruction, not a datum.** "Open PRs: 2" invites the model to keep
     its own figure alongside yours. "Open PRs RIGHT NOW: 2. Correct any memory item claiming a
     different count" is what actually overwrites the drift.

  2. **State the all-clear explicitly.** A journal records failures and never records recoveries,
     so "the review queue is backed up" survives long after the queue drained. A fact that says
     only "3 stale" leaves a memory of "12 stale" partly intact; one that says "and nothing else
     is stale" closes it.

Every probe here is wrapped in `lib.probe`, so a broken `gh` degrades to "could not verify"
instead of taking the whole consolidation down.
"""
import os, sys, json, subprocess, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import lib

STALE_DAYS = 3   # keep in step with tasks/scan.py


def _open_prs():
    repos = [r.strip() for r in (lib.env("BEADLE_REPOS", "") or "").split(",") if r.strip()]
    if not repos:
        return "BEADLE_REPOS is not set, so this employee is watching nothing at all."
    now = datetime.datetime.now(datetime.timezone.utc)
    total, stale = 0, []
    for repo in repos:
        r = subprocess.run(["gh", "pr", "list", "--repo", repo, "--state", "open",
                            "--json", "number,updatedAt,isDraft", "--limit", "100"],
                           capture_output=True, text=True, timeout=30)
        for pr in json.loads(r.stdout or "[]"):
            if pr.get("isDraft"):
                continue
            total += 1
            age = (now - datetime.datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))).days
            if age >= STALE_DAYS:
                stale.append("%s#%s (%dd)" % (repo, pr["number"], age))
    if not total:
        return ("Open non-draft PRs RIGHT NOW: 0 across %s. The review queue is EMPTY. Drop any "
                "memory item describing a backlog." % ", ".join(repos))
    return ("Open non-draft PRs RIGHT NOW: %d across %s, of which %d are stale (>=%dd): %s. Use "
            "THESE numbers and correct any memory item claiming different ones. Nothing else is "
            "stale." % (total, ", ".join(repos), len(stale), STALE_DAYS, ", ".join(stale) or "none"))


def _nagged_recently():
    p = os.path.join(lib.emp_dir("example-pr-nag"), "claims.jsonl")
    if not os.path.exists(p):
        return "This employee has never nagged about a PR, so there is no nag-to-merge rate yet."
    rows = [json.loads(l) for l in open(p) if l.strip()]
    merged = [r for r in rows if r.get("outcome") == "merged"]
    checked = [r for r in rows if r.get("outcome") is not None]
    if not checked:
        return ("%d PRs nagged, NONE reconciled yet — the nag-to-merge rate is unknown, not good. "
                "Do not claim this employee is working." % len(rows))
    return ("Nag-to-merge RIGHT NOW: %d of %d reconciled nags ended in a merge (%d%%). Use THIS "
            "rate." % (len(merged), len(checked), round(100 * len(merged) / len(checked))))


def facts():
    return [lib.probe(_open_prs), lib.probe(_nagged_recently)]
