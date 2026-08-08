---
description: Interview me, then create a new Beadle employee — role.md and a working first task.
---

Create a new employee in this repo. Read `CLAUDE.md` first, then `templates/role.md`,
`templates/task.py`, and whichever example under `employees/` is closest to what is being asked
for.

The user's request: $ARGUMENTS

## Before writing anything, get three things from the user

You cannot invent these and you must not guess them. Ask all three at once, in one message, and
wait. If the user's request above already answers one, say so and skip it.

1. **The lever.** "What number moves if this works?" If they answer with a topic ("monitor our
   competitors"), push once: a lever is *time-to-know*, *unanswered past 4 hours*, *time-to-merge*.
   Not a subject area.
2. **The recipient.** "Who receives this, and what do you expect them to do about it?" If nobody
   is named, say plainly that this employee will run perfectly and change nothing, and ask whether
   they want to continue anyway.
3. **The settled decisions.** "What has someone already suggested about this that you've decided
   against, and why?" This becomes the `Settled decisions` section. It is the difference between an
   employee that stays useful and one that re-proposes the same rejected idea every week forever.
   If they have none yet, write the section with a placeholder note saying to fill it in the first
   time they reject something twice.

Also ask what the data source is, and confirm the credential for it is **read-only**.

## Then check the request against the rubric

`docs/02-choosing-your-first-employee.md`. Score it out loud, briefly. If it fails on
**reversibility** (a wrong answer is expensive) or **on-demand vs scheduled**, say so directly and
offer the reporting-only version of the same idea instead. Do not build a customer-facing agent.

## Then write two files

- `employees/<name>/role.md` — from `templates/role.md`. The mandate must name the lever and the
  failure mode to design against. Fill `Settled decisions` from their answers.
- `employees/<name>/tasks/<task>.py` — from `templates/task.py`, or adapted from the closest
  example. Obey every rule in `CLAUDE.md`, in particular:
  - GATHER is deterministic. No model.
  - The gate is plain Python via `lib.gate()`, with named thresholds at the top of the file and a
    comment on each.
  - One `lib.llm()` call. A machine-readable first word. An explicit way to say "nothing here".
  - Check `lib.failed()`. Never deliver on `mode == "sample"`.
  - Claim only what you deliver; persist everything that passed the gate.

Pick starting thresholds deliberately and **say in a comment that they are guesses to be tuned
against a real day** — do not present a guessed number as a decision.

## Then run it and report honestly

```bash
./beadle run <name> <task>
```

Show the user the actual output. Then tell them, in plain words:

- whether the gate tripped, and whether that was correct for today
- if it tripped on a normal day, that the fix is the threshold, **not the prompt**
- that it is not finished until it produces nothing on a quiet day
- what to do next: run it by hand for a few days, then `./beadle schedule`, then add a reconciler

Do not claim it works because it ran. Say what it did.
