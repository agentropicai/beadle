# Beadle

**Perception and judgment are different systems with different costs. Build the employee that way.**

Most of any job is not thinking — it is *noticing*. Scanning, comparing against a baseline,
concluding that nothing has changed. Noticing is constant, mechanical, and answerable in SQL.
Judgment is rare, expensive, and the only part a model is good at.

Almost every agent system fuses the two: a mind wakes up every fifteen minutes to ask whether
anything happened, and you pay for a thought every time nothing did. Beadle keeps them apart.

Extracted from a fleet of five employees running a real company's operations since mid-2026.

```
git clone https://github.com/agentropicai/beadle && cd beadle
./beadle doctor                              # do the pieces work?
./beadle run example-site-watch uptime-check # a real employee, no config needed
./beadle new my-first-employee               # now write your own
```

---

## The one rule

> **The model never gathers data and never takes an action. It only judges.**

Every task in Beadle has the same four steps:

```
1. GATHER   deterministic — SQL, an API call, a shell command. No model.
2. GATE     plain Python. Did anything actually happen? If not, exit here. Most runs end here.
3. JUDGE    one model call. Tools disabled, max-turns 1. It judges the data it is handed, once.
4. DELIVER  a digest, a draft, an alert — gated, so it is silent when nothing matters.
   RECORD   journal line, archived output, commit.
```

There is no agent loop anywhere in this repo. That is not a limitation we plan to remove.

## Why it is built this way

The split is not a cost optimisation bolted onto an agent — it is the architecture, and it is
older than LLMs:

- **The reflex arc.** You do not deliberate about a hot stove. Fast paths exist so the expensive
  system is never consulted about routine input.
- **Viola–Jones (2001).** Real-time face detection worked by cascading cheap classifiers that
  reject most windows before an expensive one runs. Same shape, twenty-five years earlier.
- **Interrupts over polling.** Most of systems design is moving work off the path that runs
  constantly.

Measured on the production fleet this was extracted from — 21 live tasks, 5 employees, counted
2026-08-08:

| | |
|---|---|
| tasks that never call a model at all | **10 of 21** |
| agent loops | **0** |
| tasks whose gate can exit before any model call | **18 of 21** |
| the busiest task — 144 runs/day — costs | **zero tokens, ever** |

Three things follow, and they are the whole argument:

- **Cost.** A check with nothing to report costs nothing. There is no per-agent budget to
  govern because there is no runaway spend to govern. `llm()` shells out to `claude -p`, so it
  bills against a Claude subscription rather than per-token API credit.
- **Reliability.** Every model call in a chain is a die roll. Ten steps at 90% is 35%. Beadle
  chains are one step long.
- **Debuggability.** When a deterministic task misbehaves you read the SQL. There is no
  transcript to reconstruct and no non-determinism to reproduce.

> **Perception is constant and cheap. Cognition is rare and expensive. Don't fuse them.**

### The honest weakness

A gate that does not trip produces *silence*, and false negatives are invisible — the model never
saw the case, so nothing tells you what was missed. `DELIVER` is silent by default too, so there
are two layers of silence stacked. A model cascade at least emits a cheap auditable answer; a gate
emits nothing.

Two mitigations, both built in, and you should use both:

- **`lib.gate()` logs every decision** — what was checked, what tripped, what did not — to
  `gate.jsonl`. What was skipped, and why, stays greppable.
- **`GATE_SAMPLE`** sends a small random fraction of below-threshold runs to the judge anyway, so
  you find out what your thresholds are hiding. Set it to `0.02` and read the results monthly.

The second critique is real too: gate rules accumulate and drift, and if you are careless you end
up maintaining the rules engine you were avoiding. Keep thresholds few, named, and commented with
the false alarm that caused them.

## An employee is a folder

```
employees/<name>/
  role.md        the job description + hard guardrails       <- the file that matters
  memory.md      curated brain, re-written from the journal
  journal.jsonl  one line per run
  claims.jsonl   what it told a human, and whether that held up
  runs/          full archived output of each run
  tasks/*.py     the scheduled jobs
```

All tasks of one employee share one role, one memory, one journal. **One employee, many tasks,
one brain.**

`role.md` is a job description, not a prompt. The single most valuable section in it is the one
nobody writes on the first pass: **settled decisions the employee is forbidden to re-derive.**
Without it, a weekly employee re-proposes the same rejected idea every week, forever.

## The three things that kill an AI employee

Not model quality. These:

1. **Noise.** Your first version fires too often and after five false alarms nobody reads it.
   The fix goes in the deterministic gate, **not the prompt** — tune the SQL before you tune
   the model. (`docs/03-the-gate.md`)
2. **Nobody acts.** An employee whose output no human acts on is worth zero, and it looks
   perfectly healthy while being worthless. `lib.claim()` records what it told you;
   `reconcile` goes back later and checks reality. That number is the scorecard.
   (`docs/05-the-outcome-loop.md`)
3. **Silent death.** A token expires, a tunnel drops, a timer crashes, and nothing tells you.
   Delivery failures land in `.deliver-failures.jsonl` and `./beadle status` surfaces them.
   Your third employee should be the one that watches the other two.

## The employees that ship with it

Three, all runnable before you write a line. Read one, then delete it and write your own.

| employee | needs | shows you |
|---|---|---|
| **example-site-watch** | nothing | the gate, and the HARD/SOFT split — why a judge must only be asked what it can answer |
| **example-pr-nag** | `gh auth status` green | the full outcome loop: claim what you told a human, then check a day later whether they acted |
| **example-page-watch** | nothing | quarantine — it reads text written by competitors, so it holds no credentials and no shell |

## Guardrails, on day one

Read `docs/04-guardrails.md` before you point an employee at anything real. The short version:

- **Read-only credentials.** Not a convention — a role that cannot write.
- **Draft-and-approve.** It never publishes, deploys, pays, merges, or messages anyone outside
  its own channel.
- **If the action cannot be undone, the agent does not cross the checkpoint alone.**
- **Everything fetched is data, not instructions** — and the agent that reads untrusted content
  must not be the agent that holds privileged tools.

## Commands

```
./beadle new <name>                  scaffold an employee from templates/
./beadle run <employee> [task]       run one task, or all of them
./beadle status                      what each employee last did, and whether it is stuck
./beadle schedule <employee> <task>  print the cron / systemd lines
./beadle doctor                      check the pieces
```

Scheduling is cron or systemd timers. There is no daemon, no server, and no web UI, because
none of those are the hard part.

## Requirements

Python 3.9+ and the [Claude Code CLI](https://claude.com/claude-code) (`claude login`). That is
all — the example employee runs with no database, no API key, and no messaging setup.

## Docs

Start with **[EXAMPLE.md](EXAMPLE.md)** — a real transcript of building one employee start to
finish, including the bug hit on the way. Then **[QUICKSTART.md](QUICKSTART.md)** to do it
yourself.

| | |
|---|---|
| `docs/01-what-is-an-ai-employee.md` | the definition, and what it isn't |
| `docs/02-choosing-your-first-employee.md` | the six-point rubric — **read this before writing code** |
| `docs/03-the-gate.md` | noise, and why the fix is never the prompt |
| `docs/04-guardrails.md` | read-only, draft-and-approve, quarantine, irreversibility |
| `docs/05-the-outcome-loop.md` | the part that decides whether any of this was worth it |

## License

MIT. Built by [Agentropic](https://agentropic.ai).
