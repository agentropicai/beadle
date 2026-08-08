# The gate

The eight lines that decide whether your employee is useful or ignored.

```python
interesting = [r for r in rows if <your condition>]

if len(interesting) < MIN_ITEMS:
    lib.nothing_to_report(EMP, TASK, "nothing crossed the threshold")
```

That is the gate. It runs before any model call. On a normal day it is where the task ends.

## Why it exists

Two reasons, and the second is the one people underrate.

**Cost.** A check with nothing to report should cost nothing. In the production fleet Muster was
extracted from, 10 of 21 tasks never call a model at all, and the busiest — running 144 times a
day — has never spent a token. That is not an optimisation; it is what happens when you ask
"did anything change?" in SQL instead of in English.

**Trust.** Your employee has one resource and it is your team's willingness to still be reading
its messages in month three. Every false alarm spends some of it, and you cannot earn it back
by being right later. **A false alarm costs more than a missed blip.** Build for that ratio.

## The rule

> **When the employee is noisy, tune the SQL. Not the prompt.**

This is counterintuitive and it costs teams weeks, so it is worth stating as a law. The instinct
when an agent produces bad output is to rewrite the prompt — "be more conservative," "only alert
on serious issues," "consider whether this is normal variance." It does not work reliably,
because you are asking a judgment layer to compensate for a measurement layer that is feeding it
garbage.

A real example from the fleet. An SEO traffic-drop alert false-fired **eight days in a row**.
Every single time the cause was the same: one to three tiny pages, with baselines of five to
nine clicks a day, swinging by about three clicks — which is a 30% drop, which crossed the
threshold. The prompt was fine. The gate was wrong. The fix, in code:

```python
PAGE_BASE_MIN = 20   # ignore pages under ~20 clicks/day — below this a 3-click wiggle reads as -30%
MIN_PAGES     = 2    # a lone page's daily variance isn't sitewide news
SEVERE_ABS    = 25   # ...unless one page sheds >=25 clicks/day outright
```

Three constants and a comment. Zero prompt changes. It has not false-fired since.

## Writing a gate that survives

- **Put thresholds at the top of the file, named, with a comment.** Not inline, not in the
  prompt. You will tune them, and the comment explaining a past false alarm is worth more than
  the number.
- **Require a floor before a ratio.** Percentages on small numbers are noise generators. "20%
  down" means nothing until you also say "and it was at least N to begin with."
- **Require breadth or severity.** One item moving is variance. Either two items moved, or one
  moved a lot. This single pattern kills most false alarms.
- **Never let a broken run teach the baseline.** In the example employee, only healthy responses
  feed the latency baseline — otherwise an outage trains the employee that being broken is
  normal, and it goes quiet exactly when you need it.
- **Log the silence.** `lib.nothing_to_report()` still writes a journal line. An employee that
  leaves no trace when quiet is indistinguishable from one that has crashed.

## What the gate is not

The gate answers *did something change?* The judge answers *does it matter?* Do not push the
second question into the gate — you will end up encoding domain judgment as thresholds and it
will be brittle. And do not push the first question into the judge — that is what costs money
and produces confident nonsense on thin data.

**Give the judge only the question it can actually answer.** We shipped this wrong once: the
example employee handed a hard `HTTP 500` and a soft latency comparison to the model as one
undifferentiated "is this real?" question. It dutifully applied the small-sample caveat to the
500 — *"n=0 baseline, nothing to compare against"* — and suppressed a genuine outage. A 500 is
a measured fact, already proven by the check; there is nothing for a model to be skeptical
about. Latency-versus-baseline is a comparison, and comparisons are exactly where thin data
produces confident nonsense. The fix was to label each finding `HARD` or `SOFT` in the prompt
and tell the judge to treat them differently. See `employees/example-site-watch/tasks/uptime-check.py`.

## Calibration ritual

Run the task by hand, on a normal day, before you schedule it. It should say nothing. Do this
until it does. Then schedule it, and read every message for a week — that week is when you find
the thresholds, and there is no substitute for it.
