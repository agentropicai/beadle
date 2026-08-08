# Muster

**Build an AI employee without building an agent platform.**

An AI employee is a cron job with a job description, a memory file, and a manager. The scary
part — the agent — is about fifteen lines. Everything that makes it work is boring.

Muster is the boring part, extracted from a fleet of five employees that have been running a
real company's operations since mid-2026.

```
git clone https://github.com/agentropicai/muster && cd muster
./muster doctor                              # do the pieces work?
./muster run example-site-watch uptime-check # a real employee, no config needed
./muster new my-first-employee               # now write your own
```

---

## The one rule

> **The model never gathers data and never takes an action. It only judges.**

Every task in Muster has the same four steps:

```
1. GATHER   deterministic — SQL, an API call, a shell command. No model.
2. GATE     plain Python. Did anything actually happen? If not, exit here. Most runs end here.
3. JUDGE    one model call. Tools disabled, max-turns 1. It judges the data it is handed, once.
4. DELIVER  a digest, a draft, an alert — gated, so it is silent when nothing matters.
   RECORD   journal line, archived output, commit.
```

There is no agent loop anywhere in this repo. That is not a limitation we plan to remove.

## Why it is built this way

The usual design wakes an *agent* on a schedule and lets it decide, in the model, whether there
was anything to do — which means the deciding costs a model call whether or not anything
happened. Muster wakes a *check*. Whether anything happened is answered in Python, before any
model is involved, and the model is invoked at the judgment point and nowhere else.

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
- **Reliability.** Every model call in a chain is a die roll. Ten steps at 90% is 35%. Muster
  chains are one step long.
- **Debuggability.** When a deterministic task misbehaves you read the SQL. There is no
  transcript to reconstruct and no non-determinism to reproduce.

It is thermostat-shaped, not agent-shaped: poll constantly, call the expensive thing only when
a threshold trips.

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
   Delivery failures land in `.deliver-failures.jsonl` and `./muster status` surfaces them.
   Your third employee should be the one that watches the other two.

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
./muster new <name>                  scaffold an employee from templates/
./muster run <employee> [task]       run one task, or all of them
./muster status                      what each employee last did, and whether it is stuck
./muster schedule <employee> <task>  print the cron / systemd lines
./muster doctor                      check the pieces
```

Scheduling is cron or systemd timers. There is no daemon, no server, and no web UI, because
none of those are the hard part.

## Requirements

Python 3.9+ and the [Claude Code CLI](https://claude.com/claude-code) (`claude login`). That is
all — the example employee runs with no database, no API key, and no messaging setup.

## Docs

Start with **[QUICKSTART.md](QUICKSTART.md)** — 90 minutes, clone to scheduled.

| | |
|---|---|
| `docs/01-what-is-an-ai-employee.md` | the definition, and what it isn't |
| `docs/02-choosing-your-first-employee.md` | the six-point rubric — **read this before writing code** |
| `docs/03-the-gate.md` | noise, and why the fix is never the prompt |
| `docs/04-guardrails.md` | read-only, draft-and-approve, quarantine, irreversibility |
| `docs/05-the-outcome-loop.md` | the part that decides whether any of this was worth it |

## License

MIT. Built by [Agentropic](https://agentropic.ai).
