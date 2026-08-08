"""
Muster — the whole harness.

An employee is a folder. A task is a script. This file is everything the scripts share.

The one rule the rest of the design follows from:

    The model never gathers data and never takes an action. It only judges.

So there is no agent loop in here. `llm()` is one subprocess call with tools disabled and
max-turns 1. If you find yourself wanting to give it tools, you want a different repo.
"""
import os, sys, subprocess, json, datetime, re, html, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
EMPLOYEES = os.path.join(BASE, "employees")


# --------------------------------------------------------------------------------------
# secrets
# --------------------------------------------------------------------------------------

_env = None

def env(key, default=None):
    """Read from .env (repo root), falling back to the process environment.

    .env is gitignored. Nothing in this repo should ever read a secret from anywhere else.
    """
    global _env
    if _env is None:
        _env = {}
        p = os.path.join(BASE, ".env")
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    _env[k.strip()] = v.strip()
    return _env.get(key, os.environ.get(key, default))


# --------------------------------------------------------------------------------------
# JUDGE — the only place a model is allowed to appear
# --------------------------------------------------------------------------------------

def llm(prompt, model=None, timeout=180):
    """One-shot judgment. No tools, no loop, no retries.

    Runs `claude -p` so it bills against your Claude subscription rather than per-token API
    credit. That is deliberate: it is why this architecture needs no budget governance.

    Returns the model's text, or a string starting with "LLM_ERROR:" — never raises. Callers
    MUST check for LLM_ERROR before delivering anything. A task that delivers an error string
    to your team is worse than a task that stays silent.
    """
    model = model or env("MUSTER_MODEL", "claude-sonnet-4-6")
    try:
        r = subprocess.run(
            ["claude", "-p", "--model", model, "--max-turns", "1", "--tools", ""],
            input=prompt, capture_output=True, text=True, errors="replace", timeout=timeout,
        )
    except FileNotFoundError:
        return "LLM_ERROR: `claude` CLI not found. Install it and run `claude login`."
    except subprocess.TimeoutExpired:
        return "LLM_ERROR: timed out after %ss" % timeout

    out = (r.stdout or "").strip()
    low = out.lower()
    # Auth/quota failures come back on stdout looking like a normal short answer. Only treat
    # them as failures when the *whole* output is that message — a real answer can legitimately
    # discuss an auth error (an SRE employee triaging a 401, say) without being one.
    authfail = len(out) < 300 and any(s in low for s in (
        "invalid api key", "authentication_error", "credit balance", "usage limit",
        "organization has disabled", "oauth token", "please run /login",
    ))
    if not out or out.startswith("Error:") or authfail:
        return "LLM_ERROR: " + (out or (r.stderr or "").strip())[:300]
    return out


def failed(text):
    """True if an llm() result is an error. Use this; don't string-match by hand."""
    return isinstance(text, str) and text.startswith("LLM_ERROR:")


# --------------------------------------------------------------------------------------
# GATHER — deterministic. No model involved, ever.
# --------------------------------------------------------------------------------------

def sql(query_str, dsn=None, sep="\t"):
    """Run a read-only query via psql. Returns a list of rows (each a list of strings).

    Point MUSTER_DSN at a READ-ONLY database role. Not a convention — a credential that
    cannot write is the only version of this that survives contact with a bad week.
    """
    dsn = dsn or env("MUSTER_DSN")
    if not dsn:
        raise RuntimeError("MUSTER_DSN is not set (see .env.example)")
    r = subprocess.run(["psql", dsn, "-tA", "-F", sep, "-c", query_str],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("DB error: " + r.stderr[:300])
    return [ln.split(sep) for ln in r.stdout.strip().split("\n") if ln]


def http_json(url, headers=None, timeout=25):
    """GET a URL and parse JSON. The other half of GATHER."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def http_status(url, timeout=20):
    """Fetch a URL. Returns (status_code, elapsed_seconds, bytes, error_or_None). Never raises.

    urllib raises HTTPError on 4xx/5xx, so a naive try/except reports every server error as
    "unreachable" and any status-code logic downstream is dead code. Catch it separately and
    return the real code: an unreachable host and a 500 are different problems with different
    first-things-to-check, and collapsing them costs you that.

    A genuine connection failure (DNS, refused, timeout) returns status 0 with the error set.
    """
    started = datetime.datetime.now()
    req = urllib.request.Request(url, headers={"User-Agent": "muster/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, (datetime.datetime.now() - started).total_seconds(), len(body), None
    except urllib.error.HTTPError as ex:
        body = b""
        try:
            body = ex.read()
        except Exception:
            pass
        return ex.code, (datetime.datetime.now() - started).total_seconds(), len(body), None
    except Exception as ex:
        return 0, (datetime.datetime.now() - started).total_seconds(), 0, str(ex)[:200]


def shell(cmd, timeout=120):
    """Run a command, return stdout. For `gh`, `git`, `kubectl` and friends.

    This is GATHER, so keep it read-only. If a task needs to *change* something, that belongs
    behind a human approval, not in a gather step.
    """
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("command failed: %s\n%s" % (" ".join(cmd), r.stderr[:300]))
    return r.stdout


# --------------------------------------------------------------------------------------
# DELIVER — gated. Silence is a feature.
# --------------------------------------------------------------------------------------

def _md_to_html(text):
    """Telegram renders markdown literally unless you send HTML, and supports only a few tags."""
    out = []
    for ln in text.split("\n"):
        ln = html.escape(ln, quote=False)
        ln = re.sub(r"`([^`]+)`", r"<code>\1</code>", ln)
        ln = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", ln)
        ln = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', ln)
        h = re.match(r"^\s*#{1,6}\s+(.*)$", ln)
        ln = ("<b>%s</b>" % h.group(1)) if h else re.sub(r"^(\s*)[-*]\s+", r"\1• ", ln)
        out.append(ln)
    return "\n".join(out)


TG_LIMIT = 3800  # Telegram hard-caps at 4096; leave room for tags


def _chunks(text, limit=TG_LIMIT):
    buf = ""
    for ln in text.split("\n"):
        if buf and len(buf) + len(ln) + 1 > limit:
            yield buf
            buf = ""
        while len(ln) > limit:
            yield ln[:limit]
            ln = ln[limit:]
        buf = (buf + "\n" + ln) if buf else ln
    if buf:
        yield buf


DELIVERFAIL = os.path.join(BASE, ".deliver-failures.jsonl")


def _record_deliverfail(target, detail):
    """A dropped send used to vanish silently. That is how a dead employee looks healthy for
    six weeks. Leave a trail the fleet-health task can read."""
    try:
        with open(DELIVERFAIL, "a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().astimezone().isoformat(),
                "target": str(target), "detail": str(detail)[:160],
            }) + "\n")
    except Exception:
        pass


def deliver(text, channel=None):
    """Send a message. Channel defaults to MUSTER_CHANNEL, which defaults to the console.

    Console delivery means the repo works before you have configured anything. Switch to
    telegram/slack once the output is worth reading.
    """
    channel = channel or env("MUSTER_CHANNEL", "console")
    if channel == "console":
        print(text)
        return "console"
    if channel == "telegram":
        return _deliver_telegram(text)
    if channel == "slack":
        return _deliver_slack(text)
    _record_deliverfail(channel, "unknown channel")
    return "ERR:unknown-channel"


def _deliver_telegram(text):
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _record_deliverfail("telegram", "missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")
        return "ERR:not-configured"
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    base = {"chat_id": chat, "disable_web_page_preview": "true"}
    last = None
    try:
        for chunk in _chunks(_md_to_html(text)):
            status, body = _post(url, {**base, "text": chunk, "parse_mode": "HTML"})
            if not body.get("ok"):
                # Bad markup must never cost you the message — resend it as plain text.
                _record_deliverfail("telegram", "HTML rejected: %s" % body.get("description"))
                status, body = _post(url, {**base, "text": re.sub(r"<[^>]+>", "", chunk)})
            if status >= 300 or not body.get("ok"):
                _record_deliverfail("telegram", "HTTP %s %s" % (status, body.get("description")))
            last = status
        return last
    except Exception as ex:
        _record_deliverfail("telegram", ex)
        return "ERR:" + str(ex)[:80]


def _deliver_slack(text):
    hook = env("SLACK_WEBHOOK_URL")
    if not hook:
        _record_deliverfail("slack", "missing SLACK_WEBHOOK_URL")
        return "ERR:not-configured"
    try:
        req = urllib.request.Request(hook, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status
    except Exception as ex:
        _record_deliverfail("slack", ex)
        return "ERR:" + str(ex)[:80]


def _post(url, payload):
    data = urllib.parse.urlencode(payload).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=25) as r:
        return r.status, json.load(r)


# --------------------------------------------------------------------------------------
# RECORD — the employee's folder
# --------------------------------------------------------------------------------------

def emp_dir(emp):
    d = os.path.join(EMPLOYEES, emp)
    os.makedirs(d, exist_ok=True)
    return d


def role(emp):
    p = os.path.join(emp_dir(emp), "role.md")
    return open(p).read() if os.path.exists(p) else ""


def memory_get(emp):
    p = os.path.join(emp_dir(emp), "memory.md")
    return open(p).read() if os.path.exists(p) else "(no curated memory yet)"


def memory_set(emp, text):
    open(os.path.join(emp_dir(emp), "memory.md"), "w").write(text.strip() + "\n")


def journal(emp, task, summary):
    """One line per run. This is what makes an employee auditable, and what memory is built from."""
    rec = {"ts": datetime.datetime.now().astimezone().isoformat(),
           "task": task, "summary": str(summary)[:500]}
    open(os.path.join(emp_dir(emp), "journal.jsonl"), "a").write(json.dumps(rec) + "\n")


def journal_recent(emp, n=30):
    p = os.path.join(emp_dir(emp), "journal.jsonl")
    if not os.path.exists(p):
        return "(none)"
    out = []
    for ln in open(p).read().strip().split("\n")[-n:]:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        out.append("- %s [%s] %s" % (r.get("ts", "")[:16], r.get("task", ""), r.get("summary", "")))
    return "\n".join(out) or "(none)"


def save_run(emp, task, content):
    """Archive the full output of a run. The journal is the index; this is the transcript."""
    d = os.path.join(emp_dir(emp), "runs")
    os.makedirs(d, exist_ok=True)
    ts = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")
    p = os.path.join(d, "%s__%s.md" % (task, ts))
    open(p, "w").write(content.strip() + "\n")
    return os.path.relpath(p, BASE)


def ctx(emp, n=30):
    """The employee's context: who it is, what it has learned, what it just did.

    This is the whole memory system. It is a markdown file and a log. There is no vector
    database and you do not need one.
    """
    return ("=== ROLE ===\n%s\n\n=== CURATED MEMORY ===\n%s\n\n"
            "=== RECENT ACTIVITY (shared across this employee's tasks) ===\n%s"
            % (role(emp), memory_get(emp), journal_recent(emp, n)))


def consolidate(emp, facts=""):
    """Re-curate memory.md from the journal. Run it weekly, not every task.

    `facts` is deterministic live ground truth — pass anything you can check cheaply (open PR
    count, current queue depth, whether delivery is healthy). Memory drifts, and the fix is to
    hand it something authoritative to correct itself against, not a better prompt.
    """
    p = ("You maintain an autonomous employee's CURATED MEMORY. Given VERIFIED FACTS (live "
         "ground truth), CURRENT MEMORY and RECENT ACTIVITY, output the UPDATED memory markdown.\n"
         "Keep the same section headers that already appear in CURRENT MEMORY.\n"
         "GROUNDING RULES (critical): VERIFIED FACTS are authoritative and OVERRIDE any "
         "conflicting claim in CURRENT MEMORY — correct or DROP memory items that contradict "
         "them. Beyond that, use ONLY facts explicitly present in the sources; do NOT invent or "
         "infer timestamps, counts, names, events or urgency. If a detail is not in the source, "
         "omit it. Prefer fewer accurate items over more embellished ones.\n"
         "Merge grounded insights, close resolved threads, prune stale/duplicate/unsupported. "
         "Keep under ~1800 chars. Output ONLY the markdown.\n\n"
         "=== VERIFIED FACTS (live, authoritative — override memory on conflict) ===\n"
         + (facts or "- Now: " + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"))
         + "\n\n=== CURRENT MEMORY ===\n" + memory_get(emp)
         + "\n\n=== RECENT ACTIVITY ===\n" + journal_recent(emp, 40))
    new = llm(p, timeout=150).strip()
    if failed(new) or not new.startswith("#") or len(new) < 40:
        return False
    memory_set(emp, new)
    return True


def log(name, msg):
    d = os.path.join(BASE, "logs")
    os.makedirs(d, exist_ok=True)
    line = "%s %s" % (datetime.datetime.now().astimezone().isoformat(), msg)
    open(os.path.join(d, name + ".log"), "a").write(line + "\n")
    print(line)


def git_commit(msg):
    """Commit runtime state, so an employee's history is greppable with `git log`.

    OFF by default, and deliberately so: `git add -A` on a repo you are actively editing sweeps
    your half-finished work into a commit as a side effect of running a task. That is a nasty
    surprise on a laptop. Turn it on with MUSTER_GIT_COMMIT=1 once the employee lives on a box
    where nothing else writes to the checkout.
    """
    if env("MUSTER_GIT_COMMIT", "0") not in ("1", "true", "yes"):
        return
    if not os.path.isdir(os.path.join(BASE, ".git")):
        return
    subprocess.run(["git", "-C", BASE, "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", BASE, "commit", "-m", msg], capture_output=True)


# --------------------------------------------------------------------------------------
# The outcome loop — claims now, reality later
# --------------------------------------------------------------------------------------

def claim(emp, key, payload):
    """Record a claim this employee just made ("this needs a human"), to be checked later.

    Without this an employee can be completely useless and still look healthy: it produces
    output every day and nothing happens. See docs/05-the-outcome-loop.md.
    """
    rec = {"key": str(key), "claimed_at": datetime.datetime.now().astimezone().isoformat(),
           "outcome": None, **payload}
    open(os.path.join(emp_dir(emp), "claims.jsonl"), "a").write(json.dumps(rec) + "\n")
    return rec


def claims_due(emp, after_hours=24):
    """Claims older than `after_hours` that have not been reconciled yet."""
    p = os.path.join(emp_dir(emp), "claims.jsonl")
    if not os.path.exists(p):
        return [], []
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [json.loads(l) for l in open(p) if l.strip()]
    due = []
    for r in rows:
        if r.get("outcome") is not None:
            continue
        try:
            at = datetime.datetime.fromisoformat(r["claimed_at"])
        except Exception:
            continue
        if (now - at).total_seconds() >= after_hours * 3600:
            due.append(r)
    return rows, due


def claims_write(emp, rows):
    p = os.path.join(emp_dir(emp), "claims.jsonl")
    open(p, "w").write("".join(json.dumps(r) + "\n" for r in rows))


# --------------------------------------------------------------------------------------
# The inter-employee queue — the only channel between employees
# --------------------------------------------------------------------------------------

def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:24] or "task"


def file_task(to_emp, title, body, kind="generic", severity="normal", source="", ref=""):
    """Append a task to another employee's inbox. Deduplicated by title+ref.

    Employees do not call each other. They leave work in each other's inbox and the receiving
    employee re-judges it on its own terms — it does not trust the sender's severity.
    """
    import hashlib
    ts = datetime.datetime.now().astimezone().isoformat()
    tid = "%s-%s" % (_slug(title), hashlib.sha1((title + ref + source).encode()).hexdigest()[:8])
    rec = {"id": tid, "to": to_emp, "title": title[:200], "body": body[:2000], "kind": kind,
           "severity": severity, "source": source, "ref": ref, "status": "open", "created_at": ts}
    p = os.path.join(emp_dir(to_emp), "inbox.jsonl")
    if os.path.exists(p):
        for ln in open(p):
            try:
                r = json.loads(ln)
                if r.get("id") == tid and r.get("status") in ("open", "awaiting-approval"):
                    return tid
            except Exception:
                pass
    open(p, "a").write(json.dumps(rec) + "\n")
    return tid


def read_inbox(emp):
    p = os.path.join(emp_dir(emp), "inbox.jsonl")
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def write_inbox(emp, rows):
    p = os.path.join(emp_dir(emp), "inbox.jsonl")
    open(p, "w").write("".join(json.dumps(r) + "\n" for r in rows))


# --------------------------------------------------------------------------------------

def done(emp, task, summary, commit=True):
    """Journal + log + commit in one call. Every task should end with this or an early exit."""
    journal(emp, task, summary)
    log(task, summary)
    if commit:
        git_commit("%s %s: %s" % (emp, task, summary[:80]))


def nothing_to_report(emp, task, summary):
    """Exit silently, having left a trace. No model invoked, no message sent.

    Prefer gate() below — it does this and also records the decision.
    """
    journal(emp, task, summary)
    log(task, "silent — " + summary)
    sys.exit(0)


def gate(emp, task, tripped, summary):
    """The most important function in this file. Record the perception decision, then decide
    whether cognition is warranted.

    Returns "trip"   — the threshold was crossed; go and judge.
            "sample" — it was NOT crossed, but this run was randomly selected for audit. Judge
                       anyway, record the verdict, and DO NOT deliver.
    Exits silently otherwise.

    Why the sampling exists — this is the honest weakness of the whole design. A gate that does
    not trip produces *silence*, and false negatives are invisible: the model never saw the case,
    so nothing can tell you what you missed. A model cascade at least emits a cheap auditable
    answer; a gate emits nothing. So push a small random fraction of below-threshold runs through
    the judge anyway and read them monthly — that is how you find out what your thresholds are
    hiding. Set GATE_SAMPLE=0.02 to send 2% of quiet runs for audit.

    Every decision, tripped or not, is appended to <employee>/gate.jsonl, so what was skipped and
    why stays greppable.
    """
    import random
    rate = 0.0
    try:
        rate = float(env("GATE_SAMPLE", "0") or 0)
    except ValueError:
        pass
    sampled = (not tripped) and rate > 0 and random.random() < rate

    rec = {"ts": datetime.datetime.now().astimezone().isoformat(), "task": task,
           "tripped": bool(tripped), "sampled": bool(sampled), "summary": str(summary)[:300]}
    try:
        open(os.path.join(emp_dir(emp), "gate.jsonl"), "a").write(json.dumps(rec) + "\n")
    except Exception:
        pass

    if tripped:
        return "trip"
    if sampled:
        log(task, "gate quiet but SAMPLED for audit — " + str(summary))
        return "sample"
    journal(emp, task, summary)
    log(task, "silent — " + str(summary))
    sys.exit(0)
