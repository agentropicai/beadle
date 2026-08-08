# Quickstart — ship your first AI employee

Follow this straight through. Budget: **90 minutes** to something running on a schedule.

You need Python 3.9+ and the [Claude Code CLI](https://claude.com/claude-code), logged in.
Nothing else — no database, no API key, no Telegram.

---

## 0 · Prove the pieces work (3 min)

```bash
git clone https://github.com/agentropicai/beadle && cd beadle
./beadle doctor
```

Everything should be `ok` except `.env`, which is optional.

---

## 1 · Watch a real employee run (7 min)

```bash
./beadle run example-site-watch uptime-check
```

It says one line and exits: `silent — 1 site(s) healthy`. **No model was called.** That is the
normal case, and it is the whole architecture in one command.

Now break something on purpose:

```bash
python3 -c "
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(500); s.send_header('Content-Length','21'); s.end_headers()
        s.wfile.write(b'internal server error')
    def log_message(s,*a): pass
HTTPServer(('127.0.0.1', 8731), H).serve_forever()" &

cp .env.example .env
echo 'BEADLE_SITES=http://127.0.0.1:8731/checkout,https://example.com' >> .env
./beadle run example-site-watch uptime-check
```

Now the gate trips, the model is called exactly once, and you get a judgment. Read it — it
should have picked out the broken URL and ignored the healthy one.

```bash
cat employees/example-site-watch/claims.jsonl   # what it told you
./beadle status                                 # what it has been doing
kill %1                                         # stop the broken server
```

**What you just watched, in order:** a deterministic check found something, a plain-Python gate
decided it was worth a human, one model call turned it into a sentence, delivery happened, and a
claim was recorded so a reconciler can check later whether it held up.

---

## 2 · Decide who to hire (15 min — do not skip this)

The failure mode here is scope, not code. Read
[`docs/02-choosing-your-first-employee.md`](docs/02-choosing-your-first-employee.md) and write
one line:

> **`<Role>` watches `<data>`, every `<cadence>`, and tells `<person>` `<what>`.**

Then check it against all six:

- [ ] a recurring decision someone already makes, on data you already have
- [ ] the data is deterministically fetchable (SQL, an API, a shell command)
- [ ] a **named** human receives it and will act
- [ ] a wrong answer is cheap and reversible
- [ ] it runs on a schedule, not on demand
- [ ] you can state the ground truth for last week's answer

Six out of six or pick something else. Most first ideas score three, and finding that out now
costs fifteen minutes instead of a fortnight.

---

## 3 · Write the job description (20 min)

```bash
./beadle new support-watch     # your name here
```

Open `employees/<name>/role.md` and fill it in. This is a job description for someone you cannot
supervise minute to minute — not a prompt.

Spend the time on two sections:

- **Mandate** — name the actual lever. Not "improve support quality" but "cut the number of
  questions that sit unanswered past four hours."
- **Settled decisions — do NOT re-derive these** — this is the section nobody writes on the
  first pass and everybody needs by week three. A weekly employee will re-propose the same
  rejected idea every week, forever, unless you close it here in writing.

---

## 4 · Test the whole thing before writing any code (10 min)

Paste real data into a terminal and run the judgment by hand:

```bash
claude -p --tools "" < /tmp/my-prompt.txt
```

where the file is your `role.md` followed by the data and the question you want answered.

This tests the entire product for free, and it is where you usually discover the mandate was
wrong. Iterate here, not in code.

---

## 5 · Write the task (25 min)

```bash
cp templates/task.py employees/<name>/tasks/<task>.py
```

Fill in the four sections in order. The comments tell you what goes where.

The part to get right is **the gate** — the plain-Python condition that decides whether anything
happened. Run the task by hand, on a normal day, until it says nothing:

```bash
./beadle run <name> <task>
```

If it fires on a normal day, tune the thresholds — not the prompt. See
[`docs/03-the-gate.md`](docs/03-the-gate.md).

---

## 6 · Schedule it (5 min)

```bash
./beadle schedule <name> <task>
```

Copy the cron line, or install the systemd units it prints. Then set delivery in `.env`:

```
BEADLE_CHANNEL=telegram
TELEGRAM_BOT_TOKEN=...     # from @BotFather
TELEGRAM_CHAT_ID=...       # https://api.telegram.org/bot<TOKEN>/getUpdates
```

Give the employee **its own group**, not a shared one. One employee, one channel — so muting it
is a decision about that employee rather than about all of them.

---

## 7 · This week

- **Read every message for a week.** That week is when you find the real thresholds. There is no
  substitute for it.
- **Then add `reconcile`** — go back and check whether anyone acted on what it said. See
  [`docs/05-the-outcome-loop.md`](docs/05-the-outcome-loop.md). This is the step that tells you
  whether you built anything, and it is the step everyone skips.
- **Do not hire a second employee** until the first is reliably quiet when it should be. Two
  noisy employees are not twice as useful — they are zero, because nobody reads either.

---

## The six things to remember

1. Perception is constant and cheap. Cognition is rare and expensive. Do not fuse them.
2. The model never gathers data and never takes an action. It only judges.
3. Most runs should end at the gate, silently, having cost nothing.
4. When it is noisy, tune the SQL — not the prompt.
5. Silence hides false negatives. Set `GATE_SAMPLE` and read the audit runs monthly.
6. An employee whose output nobody acts on is a zero. Go and measure that.
