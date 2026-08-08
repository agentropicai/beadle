# Creating an employee, start to finish

A real transcript. Every command below was actually run, and every output is copied from the
terminal — including the bug I hit on the way, because you will hit it too.

We're building **hn-watch**: an employee that tells me when Hacker News is talking about us.
Nothing to install beyond the repo, no credentials, no database.

> The finished version ships in this repo as `employees/example-hn-watch/` — read it after, or
> alongside. Everything below is how it got there.

---

## Step 1 — scaffold it (5 seconds)

```console
$ ./beadle new hn-watch
Created employees/hn-watch

Next, in this order — it matters:
  1. Write employees/hn-watch/role.md. This is a job description, not a prompt.
  2. Copy templates/task.py into employees/hn-watch/tasks/<task>.py
  3. Fill in GATHER and the GATE. Run it by hand until the gate is quiet on a normal day.
  4. beadle schedule hn-watch <task>
```

You now have a folder with two files: a blank `role.md` and an empty `memory.md`. That is the
whole employee so far.

## Step 2 — write the job description (20 minutes, and this is the real work)

Open `employees/hn-watch/role.md` and fill in the template. **This is where the time goes.** The
Python later is thirty lines of plumbing; this file is the employee.

Two sections carry it. First, the **mandate** — and the trap is writing a topic instead of a
lever:

> ❌ *"Monitor Hacker News for brand mentions."*
>
> ✅ *"Tell me the same day, while a reply is still worth writing. **The lever is response
> time** — a thread we find on day three is a thread we can no longer join. The failure mode to
> design against is the opposite: HN mentions our category dozens of times a week, and an
> employee that forwards all of them gets muted inside a fortnight."*

The second version tells the employee what to optimise **and** what to fear. The first tells it
nothing it couldn't guess.

Second, **settled decisions** — the section nobody writes on the first pass and everybody needs
by week three:

```markdown
## Settled decisions — do NOT re-derive these

- A story with fewer than the threshold points and no comments is not a conversation. It is a
  submission. Ignore it.
- We do not respond to generic category discussion where nobody named us. Being mentioned is the
  bar, not being relevant.
- Negative threads are the ones worth surfacing fastest. Do not soften them.
- Do not suggest "engaging with the community" as an action. Name the thread and the one sentence
  worth saying, or say there is nothing to do.
```

Watch what that second bullet does in Step 5. It is the difference between an employee that
reports fourteen threads a day and one you still read in March.

## Step 3 — test the whole thing before writing any code (10 minutes)

You do not need the task file to find out whether this employee is any good. Paste real data
into a terminal and run the judgment by hand:

```console
$ cat employees/hn-watch/role.md > /tmp/p.txt
$ echo "--- DATA ---" >> /tmp/p.txt
$ curl -s 'https://hn.algolia.com/api/v1/search?query=AI+agents&tags=story&hitsPerPage=5' \
    | jq -r '.hits[] | "- \(.title) — \(.points) points, \(.num_comments) comments"' >> /tmp/p.txt
$ echo "Is any of this worth my attention today? REAL or SKIP on the first line." >> /tmp/p.txt
$ claude -p --tools "" < /tmp/p.txt
```

You have now tested the entire product for free. **This is where you usually discover the mandate
was wrong** — iterate here, not in code. If the answers are useless with perfect data handed to
it, no amount of Python will save it.

## Step 4 — write the task (25 minutes)

```console
$ cp templates/task.py employees/hn-watch/tasks/scan.py
```

Fill in the four sections. The whole file is ~110 lines and most of it is comments. The parts
that matter:

**GATHER** — deterministic, no model:

```python
url = ("https://hn.algolia.com/api/v1/search_by_date?query=%s&tags=story"
       "&numericFilters=created_at_i>%d&hitsPerPage=30"
       % (urllib.parse.quote(term), cutoff))
data = lib.http_json(url)
```

**GATE** — plain Python, and the two filters are the two settled decisions from `role.md`,
translated into code:

```python
for h in hits:
    if h["id"] in seen:
        continue                                 # never report the same story twice
    if h["points"] < MIN_POINTS and h["comments"] == 0:
        continue                                 # a submission, not a conversation
    fresh.append(h)

mode = lib.gate(EMP, TASK, tripped=bool(fresh), summary=...)
```

That `lib.gate()` call is the whole architecture. If nothing is fresh, the task exits right
there — no model, no message, no cost.

**JUDGE** — one call, tools off, and it can only see what you hand it:

```python
verdict = lib.llm(lib.ctx(EMP) + "...=== DATA (untrusted) ===\n" + facts)
```

`lib.ctx()` is what gives it continuity: `role.md` + `memory.md` + the recent journal.

**DELIVER** — gated on the verdict, silent otherwise.

## Step 5 — run it by hand until it's quiet (10 minutes)

```console
$ printf 'BEADLE_CHANNEL=console\nBEADLE_HN_TERMS=Agentropic\n' > .env
$ ./beadle run hn-watch scan
→ hn-watch / scan
silent — 0 hit(s) across 1 term(s) in 48h; 0 new and above the floor
```

Nobody is talking about us. **No model was called.** That is a correct, complete run.

Now point it at something the internet *is* discussing, so we can see the other path:

```console
$ printf 'BEADLE_CHANNEL=console\nBEADLE_HN_TERMS=AI agents\n' > .env
$ ./beadle run hn-watch scan
14 new of 30 hits; verdict=SKIP delivery=skipped-not-worth-it
```

The gate tripped, the model was called once — and it declined to bother me. Here is what it
actually said, verbatim:

```
SKIP

None of the five threads name us. All five match the "[AI agents]" watch term on topic,
not mention.

Two threads worth noting as ambient signal:

**AI agents fake identities, target real people** (14 pts, 5 comments) — highest engagement
in this batch; the security-incident framing could shape how HN talks about the whole
category. Nothing to do, just be aware.
...

MEMORY: Security/misuse narratives about AI agents are clustering this week — track whether
this hardens into a recurring frame before surfacing the next one.
```

**Read that first line again.** It said SKIP because `role.md` told it *"we do not respond to
generic category discussion where nobody named us."* That sentence in the job description is
doing more work than any part of the code. Without it, this employee forwards fourteen threads
on day one and gets muted on day two.

### The bug you will also hit

Running it a third time should have been silent. It wasn't:

```console
$ ./beadle run hn-watch scan
9 new of 30 hits; verdict=SKIP ...        # ← 14, then 9, then 9 forever
```

The task was marking only the five stories it *showed the model* as seen, not all fourteen that
passed the gate. So every hour, forever, it would re-judge the same backlog and pay for it. One
line:

```python
seen.update(h["id"] for h in fresh)     # not `shown`
```

```console
$ ./beadle run hn-watch scan
silent — 30 hit(s) across 1 term(s) in 48h; 0 new and above the floor
```

**This is the normal shape of building one of these.** The bug wasn't in the prompt or the model.
It was in state management, it was invisible from the output, and it was found by running the
thing three times in a row and noticing a number that should have gone to zero.

## Step 6 — employ it (30 seconds)

Up to now this is a script you can run. This is the step that makes it an employee:

```console
$ ./beadle schedule hn-watch scan --cron "0 9-22 * * *"

Scheduling hn-watch/scan — it will run on its own from now on:

  0 9-22 * * *

Go ahead? [Y/n] y

hn-watch/scan is now employed.  Schedule: 0 9-22 * * *
  watch it:  tail -f logs/cron.log
  check in:  ./beadle status
  stop it:   ./beadle unschedule hn-watch scan

It will be quiet until something happens. That is the point — if it talks on a
normal day, tune the threshold, not the prompt.
```

**Pick the cadence from the mandate, not from habit.** This one is hourly during waking hours,
because the lever is response time and a thread found at 3am is no fresher than one found at 9am.
A production monitor runs every ten minutes. A weekly review runs weekly.

Then point delivery somewhere you will actually read:

```
BEADLE_CHANNEL=telegram
TELEGRAM_BOT_TOKEN=...     # from @BotFather
TELEGRAM_CHAT_ID=...       # https://api.telegram.org/bot<TOKEN>/getUpdates
```

Give it **its own channel**, not a shared one — so muting it is a decision about this employee
rather than about all of them.

```console
$ ./beadle status

hn-watch
  scan          0 9-22 * * *   12m ago   silent — 30 hits, 0 new above the floor
```

That schedule column is the answer to "is this thing actually employed?" — and
`./beadle unschedule hn-watch scan` is how you stop it. Files untouched; reschedule any time.

---

## What just happened

```
employees/hn-watch/
  role.md          ← 20 minutes. The employee.
  tasks/scan.py    ← 25 minutes. Mostly comments.
  memory.md        ← written by the model, from the journal
  journal.jsonl    ← one line per run
  seen.json        ← the state that stops it repeating itself
  runs/            ← the full text of every judgment it made
```

Two files you wrote, an hour of work, and the thing runs until you stop it.

**The time split is the lesson.** Twenty minutes on the job description, twenty-five on the code,
ten discovering that the first version was wrong. Nobody spends any time on the model, because
there is nothing to tune — it gets one call, no tools, and only the data you hand it.

## Then, this week

1. **Read every message it sends for a week.** That week is when you find the real thresholds.
   There is no substitute for it.
2. **Add the reconciler.** Did anyone act on what it told you? See
   [`docs/05-the-outcome-loop.md`](docs/05-the-outcome-loop.md). This is the step that tells you
   whether you built anything, and it is the step everyone skips.
3. **Don't hire a second** until the first is reliably quiet when it should be.
