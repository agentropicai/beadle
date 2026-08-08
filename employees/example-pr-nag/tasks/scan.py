#!/usr/bin/env python3
"""
pr-nag — find tested work rotting in the review queue.

GATHER  `gh pr list` on each repo in BEADLE_REPOS (deterministic; no model).
GATE    a PR is "stale" if it is non-draft, untouched for >= STALE_DAYS, and not already
        nagged today. Nothing stale -> exit before any model call.
JUDGE   one-shot: which ONE matters most today, and how to say it.
DELIVER only when there is something. Records a claim so `reconcile` can check if it merged.

READ-ONLY: `gh pr list` / `gh pr view` only. Never merges, comments or pushes.

Setup: `gh auth status` must be green. Set BEADLE_REPOS=owner/repo,owner/other in .env
"""
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import lib

EMP = "example-pr-nag"
TASK = "scan"

# --- thresholds, named and explained ----------------------------------------------------
STALE_DAYS = 3     # a PR untouched this long is waiting on a human, not on work
MAX_REPORT = 6     # never hand the model more than this; a wall of PRs produces a wall of prose

REPOS = [r.strip() for r in (lib.env("BEADLE_REPOS", "") or "").split(",") if r.strip()]
if not REPOS:
    lib.log(TASK, "BEADLE_REPOS is not set — nothing to watch. See .env.example")
    sys.exit(0)


# =======================================================================================
# 1. GATHER — deterministic
# =======================================================================================
now = datetime.datetime.now(datetime.timezone.utc)
prs = []

for repo in REPOS:
    try:
        # `--search sort:updated-asc` is load-bearing, not a flourish. `gh pr list` defaults to
        # newest-first, so on a busy repo a plain --limit fetches exactly the PRs that CANNOT be
        # stale and the employee reports "all healthy" forever. Sort oldest-touched first so the
        # limit truncates the boring end instead of the interesting one. Cost us one silent run.
        out = lib.shell(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "60",
                         "--search", "sort:updated-asc",
                         "--json", "number,title,author,isDraft,updatedAt,reviewDecision,url"])
    except Exception as ex:
        # A repo we can't read is a fact worth journalling, not a crash that kills the run.
        lib.journal(EMP, TASK, "could not read %s: %s" % (repo, str(ex)[:120]))
        continue
    for pr in json.loads(out or "[]"):
        try:
            updated = datetime.datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        except Exception:
            continue
        prs.append({
            "repo": repo, "number": pr["number"], "title": pr["title"],
            "author": (pr.get("author") or {}).get("login", "?"),
            "draft": pr.get("isDraft", False),
            "review": pr.get("reviewDecision") or "NONE",
            "days": (now - updated).total_seconds() / 86400,
            "url": pr.get("url", ""),
        })


# =======================================================================================
# 2. GATE — perception. Most days this is where the task ends.
# =======================================================================================
# Three exclusions, each one a settled decision from role.md rather than a hunch:
#   - drafts are not late, they are drafts
#   - CHANGES_REQUESTED is waiting on the author, which is a different problem
#   - anything touched recently is alive
stale = [p for p in prs
         if not p["draft"]
         and p["review"] != "CHANGES_REQUESTED"
         and p["days"] >= STALE_DAYS]
stale.sort(key=lambda p: -p["days"])

mode = lib.gate(EMP, TASK, tripped=bool(stale),
                summary="%d open PR(s) across %d repo(s), %d stale >=%dd"
                        % (len(prs), len(REPOS), len(stale), STALE_DAYS))


# =======================================================================================
# 3. JUDGE — one call, tools off
# =======================================================================================
shown = (stale or prs)[:MAX_REPORT]
facts = "\n".join(
    "- %s#%d (%.1f days idle, review=%s, by @%s): %s"
    % (p["repo"], p["number"], p["days"], p["review"], p["author"], p["title"][:90])
    for p in shown)

prompt = lib.ctx(EMP) + (
    "\n\n=== TASK: scan (daily) ===\n"
    "The PRs below have been open and untouched for at least %d days. They are already "
    "confirmed stale by a deterministic check — do NOT re-argue whether they are old.\n"
    "Your job: pick the ONE that most deserves a human's attention today, and say why in a "
    "sentence someone can act on. Consider what the CURATED MEMORY says about which ones have "
    "already been nagged (escalate the tone, don't repeat yourself) and which are parked for a "
    "stated reason.\n"
    "Your FIRST line must be exactly one bare word, no markdown, no punctuation: NAG or HOLD.\n"
    "HOLD only if memory says every one of these is parked for a reason that still applies.\n"
    "Then a blank line, then: the repo#number, who it is waiting on, how long, and one line on "
    "why it matters. Then, if there are others, one short list of the rest by age.\n"
    "Do not propose process changes, review SLAs, or adding reviewers. Name the PR and the "
    "person. Output <=900 chars.\n"
    "End with a line: MEMORY: <one durable learning>\n\n"
    "=== DATA ===\n" % STALE_DAYS + facts
)

verdict = lib.llm(prompt)
if lib.failed(verdict):
    lib.done(EMP, TASK, "skipped — " + verdict[:120], commit=False)
    sys.exit(0)

run_path = lib.save_run(EMP, TASK, verdict)
first_word = verdict.strip().lstrip("*_# ").upper()


# =======================================================================================
# 4. DELIVER
# =======================================================================================
if mode == "sample":
    lib.done(EMP, TASK, "GATE AUDIT (nothing stale): judge said %s. saved=%s"
             % (first_word.split()[0][:4] if first_word else "?", run_path), commit=False)
    sys.exit(0)

if first_word.startswith("HOLD"):
    status = "held"
else:
    status = lib.deliver("*pr-nag — work waiting on a human*\n\n" + verdict[:3500])
    # Claim only what we actually told a human about — `shown`, not every stale PR. A claim is a
    # promise to check later whether someone acted; claiming 60 PRs after naming 6 would make the
    # nag-to-merge rate measure the repo's background merge activity instead of this employee's
    # effect on it. Measure what you did, not what you saw.
    for p in shown:
        lib.claim(EMP, key="%s#%d" % (p["repo"], p["number"]),
                  payload={"days": round(p["days"], 1), "author": p["author"], "url": p["url"]})


# =======================================================================================
# 5. RECORD
# =======================================================================================
lib.done(EMP, TASK, "%d stale of %d open; verdict=%s delivery=%s saved=%s"
         % (len(stale), len(prs), first_word.split()[0][:4] if first_word else "?",
            status, run_path))
