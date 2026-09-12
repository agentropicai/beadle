# Beadle — working rules

Read `EXAMPLE.md` for a worked end-to-end build. This file is the rules for writing employees in
this repo. Gotchas only — everything derivable from `ls` or from reading `lib.py` is omitted.

## The one rule everything else follows from

**The model never gathers data and never takes an action. It only judges.**

Every task is `GATHER → GATE → JUDGE → DELIVER → RECORD`. There is no agent loop in this repo and
adding one is not a fix. If you are reaching for tools in the judge step, the task is wrong.

## Writing a task — the mistakes to avoid

These are the failure modes seen repeatedly. Each one produces code that runs and looks fine.

- **Do not put the "did anything happen?" decision in the prompt.** It goes in `lib.gate()`, in
  plain Python, before any model call. A task whose gate is `tripped=True` is not using the
  architecture.
- **Do not ask the judge a question it cannot answer.** Separate hard facts (a 500, a DNS
  failure, a count) from soft comparisons (slower than baseline, more than usual). Hard facts are
  already proven — tell the model so, or it will apply small-sample scepticism to a measured fact
  and suppress a real event. `example-site-watch` labels each finding `HARD` or `SOFT` for exactly
  this reason.
- **Force a machine-readable first line** (`REAL`/`NOISE`, `NAG`/`HOLD`, `WORTH`/`SKIP`) so
  DELIVER can gate on it without parsing prose. And always give the judge an explicit way to say
  "this is nothing" — a judge that cannot decline is a rubber stamp.
- **Claim only what you delivered.** `lib.claim()` is a promise to check later whether a human
  acted. Claiming everything you *saw* rather than everything you *reported* makes the action rate
  measure background activity instead of this employee's effect.
- **Persist what you have already reported, for everything that passed the gate** — not just the
  subset you showed the model. Otherwise the remainder stays permanently "new" and every run
  re-judges the same backlog. (See the bug in `EXAMPLE.md`.)
- **Never deliver on a `mode == "sample"` run.** Those are gate audits; they exist to reveal what
  the thresholds hide, not to route around them.
- **Always check `lib.failed(verdict)`** before delivering. Never send an `LLM_ERROR:` string to a
  human, and never swallow it silently — journal it so a fleet-health task can see the employee is
  broken.
- **Thresholds go at the top of the file, named, with a comment saying which false alarm caused
  them.** When the employee is noisy the fix is here, not in the prompt.

## Ground facts (`employees/<name>/facts.py`)

`consolidate()` calls `ground_facts()` automatically. Everything below is about the employee's
own `facts.py`, which adds to the four `default_facts()` every employee already gets.

- **Write the fact as an instruction, not a datum.** `Open PRs: 2` lets the model keep its own
  figure next to yours; `Open PRs RIGHT NOW: 2. Correct any memory item claiming a different
  count` is what actually overwrites the drift.
- **Say the all-clear out loud.** Journals record failures and never recoveries, so a resolved
  problem stays in memory indefinitely. A fact must be able to say "nothing is stale" / "delivery
  is healthy, drop any thread claiming otherwise", or memory only ever accumulates.
- **Wrap every probe in `lib.probe()`.** It cannot raise, and "could not verify" is an honest
  fact. Omitting a failed check silently reads to the model as "no problem here".
- **Ground anything memory has been caught inventing.** Counts, queue depths, whether an
  integration is broken. If you have corrected memory about it twice by hand, it is a fact.
- Facts are for what you can check cheaply and deterministically. A probe that needs a model is
  not a fact, it is another task.

## Writing role.md

- The mandate must name **the lever** — the number that moves if this works — not the topic.
  "Monitor X" is a topic. "Cut the time between a customer complaining and us knowing" is a lever.
- The `Settled decisions` section is not optional and cannot be invented by an LLM: it is the list
  of ideas the human has already rejected, with reasons. Without it a scheduled employee
  re-proposes the same rejected idea every run, forever. Ask the human for it.
- `Must NOT` is written in the imperative and is specific enough to point at during a review.

## Guardrails that are not negotiable

- **Read-only credentials**, enforced by the credential, not by prose. A rule that must be
  *prevented* rather than *discouraged* belongs in a permission, not in `role.md`.
- **Draft-and-approve.** No task publishes, deploys, pays, merges, sends, or messages anyone
  outside its own channel.
- **If an action cannot be undone, the employee does not take it.** It asks.
- **An employee that reads untrusted content holds no credentials and no shell.** Mark such data
  explicitly as untrusted in the prompt and say so in `role.md`. See `docs/04-guardrails.md`.

## Conventions

- One employee = one folder under `employees/`. Tasks share one role, one memory, one journal.
- Runtime state (`journal.jsonl`, `claims.jsonl`, `gate.jsonl`, `runs/`, `memory.md`, snapshots,
  seen-state) is gitignored and written by tasks. Never hand-edit it.
- Config comes from `.env` via `lib.env()` with a `BEADLE_` prefix. Document any new key in
  `.env.example`.
- Model access is provider-neutral and subscription-backed. `BEADLE_LLM_PROVIDER` selects
  `claude` or `codex`; `BEADLE_LLM_FALLBACK` may name the other. Keep both paths behind
  `lib.llm()` and preserve its `LLM_ERROR:` contract. Never add an API-key dependency.
- `lib.git_commit()` is off unless `BEADLE_GIT_COMMIT=1` — on a checkout someone is editing, it
  would sweep their work into a commit.

## Verify

```bash
./beadle doctor                     # are the pieces working
./beadle run <employee> <task>      # run once, by hand
./beadle status                     # what each employee last did
```

A new task is not finished when it produces output. It is finished when it produces **nothing** on
a normal day. Run it by hand until that is true, then schedule it:

```bash
./beadle schedule <employee> <task> --cron "30 9 * * *"   # installs it, after confirming
./beadle unschedule <employee> <task>                     # stop it; files untouched
```

`schedule` installs by default — an employee that is not scheduled is not an employee. Derive the
cadence from the mandate rather than defaulting to every ten minutes, and say which you chose.
`./beadle status` shows the schedule next to each task, so "is this thing actually employed?" is
answerable at a glance.
