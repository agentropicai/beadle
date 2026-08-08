# What an AI employee is

Not a chatbot. Not a copilot. Not a dashboard.

A copilot waits for a prompt. An employee owns a workflow.

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
