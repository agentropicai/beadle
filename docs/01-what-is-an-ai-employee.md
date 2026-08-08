# What an AI employee is

Not a chatbot. Not a copilot. Not a dashboard.

A copilot waits for a prompt. An employee owns a workflow.

More precisely: **an AI employee is a standing question your company asks continuously, and a
judgment that gets made only when the answer changes.**

That definition is doing real work. It separates the two halves of any job — the *noticing*,
which is constant and mechanical, and the *thinking*, which is rare and expensive. Hold those
apart and everything else in this repo follows.

## Seven properties

If the thing you are building is missing one of these, it is a script or a demo. That is fine —
just do not schedule it and expect it to behave like staff.

| | |
|---|---|
| **a role** | a name, a job description, a lane |
| **responsibilities it owns** | end to end, not suggestions |
| **tools and access** | inside the systems you already run |
| **a cadence** | hourly, daily, weekly — it runs whether or not you remember it |
| **judgment boundaries** | it acts alone where it is proven, asks where it is not |
| **an escalation path** | exceptions reach a human before they become surprises |
| **a scorecard** | output you can measure against the human baseline |

And one thing no software has had before: **it apprentices.** A correction from your best person
lands in `memory.md`, the next run reads it, and the behaviour is permanent. The hundredth week
is better than the first.

## What it is not

- **Not an agent that figures things out.** It follows a fixed four-step shape. The intelligence
  is in the judgment step and nowhere else.
- **Not a replacement for a person.** It is the recurring, schedulable, low-judgment 20% of a
  person's week, taken off their plate and made auditable.
- **Not autonomous.** Almost everything it produces is a draft. That is the design, not a
  limitation to grow out of. See `04-guardrails.md`.

## The shape of the work

```
GATHER   deterministic. SQL, an API pull, a shell command. No model.
GATE     plain Python. Did anything happen? If not, stop here — silently.
JUDGE    one model call, tools off. It judges what you hand it, once.
DELIVER  gated. Silence is the correct output most days.
RECORD   journal, archive, commit.
```

Read that again with an eye on where the model appears: **once, in the middle, on data it did
not fetch, producing text that does not act.** Everything unpleasant about running agents in
production comes from violating one of those four constraints.

## "So it's cron with an LLM in it"

Cron is the clock. It is not the architecture.

The architecture is the split: perception is constant and cheap, cognition is rare and expensive,
and they are different systems. Almost every agent platform fuses them — a mind wakes on a timer
to ask whether anything happened, and you pay for a thought every time nothing did. Take that
fusion out and you do not get a simpler agent. You get a system that can run for a year without
anyone watching it, on a bill that does not scale with how often you check.

The lineage is older than LLMs: the reflex arc (you do not deliberate about a hot stove), the
Viola–Jones cascade (cheap classifiers reject most windows before an expensive one runs),
interrupts over polling. This is a well-worn idea arriving somewhere new.
