# The outcome loop

The part that decides whether any of this was worth building. Skip it and you will not find out
for six months.

## The problem

An employee that produces plausible output on schedule looks identical, from the outside, to an
employee that is useful. Both run green. Both write journal lines. Both deliver something every
morning. One of them is changing the company and the other is generating well-formatted text
that nobody acts on, and **you cannot tell which by reading the output** — the output is
persuasive in both cases.

This is the same failure as judging a model by whether its answer reads well. Fluency is the
default. Correctness, and usefulness, are things you have to go and check.

## The loop

```
run        → journal.jsonl    what I did
claim      → claims.jsonl     what I told a human needed attention
reconcile  → ≥24h later, go and look at reality: did it hold up? did anyone act?
             → write the outcome back, compute a rate
consolidate→ re-curate memory.md from the journal, grounded in verified facts
next run   → ctx() = role + memory + recent journal
```

**Act → record the claim → check reality → fold into memory → the next run is smarter.**

No platform gives you this, and it is not because platforms are lazy. Reconciliation is domain
logic: only you know what "the team acted on it" looks like in your database. It is a SQL query
you write once, and it is the most valuable file in your employee's folder.

## In code

Record a claim when the employee tells a human something needs attention:

```python
lib.claim(EMP, key=chat_id, payload={"reason": "unanswered >4h", "url": ...})
```

Then a separate task, on a slower cadence, goes and looks:

```python
rows, due = lib.claims_due(EMP, after_hours=24)
for c in due:
    # deterministic re-check against the real system — no model here
    c["outcome"] = "answered" if ... else "still_open"
lib.claims_write(EMP, rows)
```

There is deliberately no model call in a reconciler. This is the part of an AI employee that
has nothing to do with AI.

## The two rates

Which one you want depends on what the employee claims.

**Action rate** — for employees that ask a human to do something.
*Of the things it flagged, how many did somebody act on?*

Bucket the outcomes rather than making them binary. The community-manager employee in the
original fleet resolves each flag to `answered` / `routed` / `doctor_assigned` /
`activity_after` / `still_open`, and counts the first four as acted-on. The buckets are where
the diagnosis lives.

**Alert precision** — for employees that claim something is wrong.
*Of the alerts it sent, how many were still true an hour later?*

The example employee that ships with Beadle computes this one, because it is the fastest
feedback you can get on a gate.

## Reading the number

This is the part that gets misread, so be careful:

- **Low precision → your gate is too twitchy.** Go tune the thresholds in `03-the-gate.md`. This
  is not a model problem and rewriting the prompt will not fix it.
- **High `still_open` → one of two things,** and you must work out which before acting: either
  the flags are noise (same fix as above), or the flags are real and **your team is not acting
  on them.** The second is a much more important finding than anything the employee was built to
  report, and you would never have learned it otherwise.
- **A rate you never look at is worth nothing.** Put it in the weekly digest.

## Memory drifts, and a better prompt will not fix it

The last step of the loop is `consolidate()`, which re-curates `memory.md` from the journal. Left
alone it develops a specific and dangerous failure: **it starts remembering a number instead of
checking it.** An employee that watched eight open pull requests keeps reporting eight for weeks
after six of them merged, because nothing ever contradicts it. Worse, the journal only records
failures, never recoveries, so "delivery is broken" and "that unit keeps crashing" survive long
after both were fixed, and every digest built on that memory inherits the error.

The fix is not prompt engineering. It is handing the model something authoritative to correct
itself against, every single time it curates:

```python
lib.consolidate(EMP)          # calls ground_facts(EMP) for you
```

`ground_facts` returns what is true *right now*, and the consolidation prompt states that these
override anything in memory that disagrees. Every employee gets four for free from
`default_facts()`: the time, whether delivery actually works, its own action rate from
`claims.jsonl`, and **whether its own tasks are erroring**: the one thing an employee cannot see
about itself, and the reason a fleet can sit dead for a week while its memory reads healthy.

Add your own in `employees/<name>/facts.py`, defining `facts()` returning a list of strings. See
`example-pr-nag/facts.py`. Two rules, both learned by getting them wrong:

- **Phrase a fact as an instruction, not a datum.** `Open PRs: 2` invites the model to keep its
  own figure alongside yours. `Open PRs RIGHT NOW: 2. Correct any memory item claiming a
  different count` is what overwrites the drift.
- **State the all-clear explicitly.** A fact that says "3 are stale" leaves a memory of "12 are
  stale" partly standing. One that ends "nothing else is stale" closes it.

Wrap each probe in `lib.probe()`. It never raises, and it degrades to "could not verify", which
is an honest fact. Silently omitting a failed check reads to the model as "no problem here".

### The failure this prevents, in full

A real one, worth reading as a whole. A monitoring employee had ten checks pointing at servers
that had been decommissioned. They failed on every run for eight days and 1,185 runs. Nobody was
lying and nothing was hidden: the alerts fired, the journal recorded them, and the employee
faithfully summarised them every ten minutes.

Then its memory consolidated the pattern into a learning: *"prod-monitor: 49 checks; steady-state
10 failing."* Followed by a hand-maintained list of "benign flaps" to ignore. The employee had
taught itself that red was normal, which is exactly what a human does with an alarm that goes off
every day, and it did it in under a week.

**A gate with too many false positives teaches the agent to route around it.** A check nobody
trusts is worse than no check, because it also occupies the slot where a real check would go. The
ground fact that fixes this does not just state the count; it states the rule: *a failing check is
an outage or a broken check, never a steady state.*

## Closing the loop on the humans too

The original fleet needed one more task that nobody plans for: a `stale-work` employee that nags
humans about agent-opened pull requests nobody has merged, escalating by age. Tested fixes were
rotting un-merged for weeks — the agent had done its job perfectly and the value was sitting in
a queue.

If your employee's output requires a human step to become real, something has to watch that
step. Otherwise you have automated the production of work and left the consumption of it
entirely to goodwill.

## When to build it

Week two. Not later, and not first.

Week one you are finding out whether the gate is quiet on a normal day. Week two you find out
whether anyone cares about what it says when it is not.
