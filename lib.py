"""
Beadle — the whole harness.

An employee is a folder. A task is a script. This file is everything the scripts share.

The one rule the rest of the design follows from:

    The model never gathers data and never takes an action. It only judges.

So there is no agent loop in here. `llm()` is one subprocess call with tools disabled and
max-turns 1. If you find yourself wanting to give it tools, you want a different repo.
"""
import os, sys, subprocess, json, datetime, re, html, shutil, tempfile, urllib.request, urllib.parse, importlib.util

# Where the workspace lives. Defaults to this file's directory, which is what you want when lib.py
# sits in the workspace you cloned. Set BEADLE_HOME when it does not: `pip install beadle` ships
# this same file as `beadle.lib`, and an existing codebase can then import the harness while
# keeping its employees, .env and logs in its own repo instead of in site-packages.
#
# BEADLE_EMPLOYEES is separate because a consumer may already have a layout: point it at the repo
# root and pass employee names with a prefix ("gagahealth/sre") rather than reorganising folders.
BASE = os.environ.get("BEADLE_HOME") or os.path.dirname(os.path.abspath(__file__))
EMPLOYEES = os.environ.get("BEADLE_EMPLOYEES") or os.path.join(BASE, "employees")


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

PROVIDERS = ("claude", "codex")


def llm_providers():
    """Configured subscription-backed CLI providers, primary first.

    BEADLE_LLM_PROVIDER chooses the primary. BEADLE_LLM_FALLBACK is optional and is only
    attempted when the primary returns an actual CLI/auth/quota error. No API credentials are
    read or used by this harness.
    """
    primary = (env("BEADLE_LLM_PROVIDER", "claude") or "claude").strip().lower()
    fallback = (env("BEADLE_LLM_FALLBACK", "") or "").strip().lower()
    names = [primary] + ([fallback] if fallback else [])
    bad = [name for name in names if name not in PROVIDERS]
    if bad:
        raise ValueError("unsupported BEADLE LLM provider: %s (choose claude or codex)" % bad[0])
    return list(dict.fromkeys(names))


def llm_provider():
    """The configured primary provider."""
    return llm_providers()[0]


def _provider_model(provider, requested=None):
    """Resolve a model without leaking a vendor-specific model name into the other CLI."""
    specific = env("BEADLE_%s_MODEL" % provider.upper())
    candidate = specific or requested or env("BEADLE_MODEL")
    if candidate:
        low = candidate.lower()
        if provider == "codex" and (low.startswith("claude") or low in ("opus", "sonnet", "haiku")):
            candidate = None
        elif provider == "claude" and low.startswith(("gpt-", "o1", "o3", "o4", "codex")):
            candidate = None
    if provider == "claude":
        return candidate or "claude-sonnet-4-6"
    # An omitted Codex model deliberately uses the model included with the logged-in account.
    return candidate


def _provider_cli(provider):
    key = "BEADLE_%s_BIN" % provider.upper()
    return env(key) or shutil.which(provider) or provider


def subscription_env(provider, base=None):
    """Environment for a subscription login, with API/provider overrides removed.

    Both CLIs prefer some environment credentials over their saved interactive login. Removing
    those variables here makes the no-API contract executable rather than merely documented.
    The login stores themselves (Claude config and CODEX_HOME) remain available.
    """
    if provider not in PROVIDERS:
        raise ValueError("provider must be claude or codex")
    clean = dict(base if base is not None else os.environ)
    if provider == "claude":
        for key in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
            clean.pop(key, None)
    else:
        clean.pop("OPENAI_API_KEY", None)
    return clean


def _short_error(provider, r, stdout=None):
    out = (stdout if stdout is not None else r.stdout or "").strip()
    detail = out or (r.stderr or "").strip() or "no output"
    return "LLM_ERROR: %s: %s" % (provider, detail[:300])


def _looks_like_cli_error(text):
    low = (text or "").strip().lower()
    return len(low) < 500 and any(s in low for s in (
        "invalid api key", "authentication_error", "credit balance", "usage limit",
        "weekly limit", "rate limit", "organization has disabled", "oauth token",
        "please run /login", "please run `claude`", "not logged in", "login required",
        "you've hit your", "you have hit your",
    ))


def _claude(prompt, model, timeout):
    cli = _provider_cli("claude")
    try:
        r = subprocess.run(
            [cli, "-p", "--model", model, "--max-turns", "1", "--tools", "",
             "--output-format", "json"],
            input=prompt, capture_output=True, text=True, errors="replace", timeout=timeout,
            env=subscription_env("claude"),
        )
    except FileNotFoundError:
        return ("LLM_ERROR: claude: CLI not found at %r. Install it and run `claude auth login`, or "
                "set BEADLE_CLAUDE_BIN." % cli)
    except subprocess.TimeoutExpired:
        return "LLM_ERROR: claude: timed out after %ss" % timeout

    raw = (r.stdout or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        if r.returncode != 0 or not raw or _looks_like_cli_error(raw):
            return _short_error("claude", r, raw)
        return raw
    if isinstance(data, dict) and "result" in data:
        out = str(data.get("result") or "").strip()
        if (r.returncode != 0 or data.get("is_error") or data.get("api_error_status") is not None
                or data.get("subtype") not in (None, "success") or _looks_like_cli_error(out)):
            return _short_error("claude", r, out)
        return out or _short_error("claude", r, "empty result")
    if r.returncode != 0 or not raw:
        return _short_error("claude", r, raw)
    return raw


def _codex(prompt, model, timeout):
    cli = _provider_cli("codex")
    cmd = [cli, "exec", "--ephemeral", "--ignore-user-config",
           "-c", 'forced_login_method="chatgpt"', "-c", 'approval_policy="never"',
           "-c", "tools.web_search=false", "-c", "tools.view_image=false",
           "--disable", "shell_tool", "--disable", "unified_exec", "--ignore-rules",
           "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never"]
    if model:
        cmd += ["--model", model]
    cmd.append("-")
    # Keep the judge in an empty, read-only workspace. Even though Codex is an agentic CLI, it has
    # no repo or credentials to inspect here; the prompt is the complete input to this judgment.
    try:
        with tempfile.TemporaryDirectory(prefix="beadle-judge-") as workdir:
            r = subprocess.run(cmd, input=prompt, cwd=workdir, capture_output=True, text=True,
                               errors="replace", timeout=timeout, env=subscription_env("codex"))
    except FileNotFoundError:
        return ("LLM_ERROR: codex: CLI not found at %r. Install it and run `codex login`, or set "
                "BEADLE_CODEX_BIN." % cli)
    except subprocess.TimeoutExpired:
        return "LLM_ERROR: codex: timed out after %ss" % timeout

    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out or _looks_like_cli_error(out):
        return _short_error("codex", r, out)
    return out


def llm(prompt, model=None, timeout=180, provider=None):
    """One-shot judgment through a logged-in Claude or Codex CLI.

    The primary provider comes from BEADLE_LLM_PROVIDER. Set BEADLE_LLM_FALLBACK to the other
    provider for quota/auth failover. `model` remains backward compatible: a Claude model is
    ignored when Codex is active and vice versa; provider-specific environment settings win.

    Returns the model's text, or a string starting with "LLM_ERROR:" — never raises for CLI
    failures. Callers MUST check it before delivery.
    """
    try:
        providers = [provider.strip().lower()] if provider else llm_providers()
        if any(name not in PROVIDERS for name in providers):
            raise ValueError("provider must be claude or codex")
    except (AttributeError, ValueError) as exc:
        return "LLM_ERROR: configuration: %s" % exc

    errors = []
    for index, name in enumerate(providers):
        selected_model = _provider_model(name, model)
        result = (_claude(prompt, selected_model, timeout) if name == "claude"
                  else _codex(prompt, selected_model, timeout))
        if not failed(result):
            if index:
                print("beadle: %s failed; judgment completed with %s fallback" %
                      (providers[0], name), file=sys.stderr)
            return result
        errors.append(result[len("LLM_ERROR: "):])
    return "LLM_ERROR: " + " | fallback: ".join(errors)


def failed(text):
    """True if an llm() result is an error. Use this; don't string-match by hand."""
    return isinstance(text, str) and text.startswith("LLM_ERROR:")


# --------------------------------------------------------------------------------------
# GATHER — deterministic. No model involved, ever.
# --------------------------------------------------------------------------------------

def sql(query_str, dsn=None, sep="\t"):
    """Run a read-only query via psql. Returns a list of rows (each a list of strings).

    Point BEADLE_DSN at a READ-ONLY database role. Not a convention — a credential that
    cannot write is the only version of this that survives contact with a bad week.
    """
    dsn = dsn or env("BEADLE_DSN")
    if not dsn:
        raise RuntimeError("BEADLE_DSN is not set (see .env.example)")
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
    req = urllib.request.Request(url, headers={"User-Agent": "beadle/1.0"})
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


def deliver(text, channel=None, webhook=None):
    """Send a message. Channel defaults to BEADLE_CHANNEL, which defaults to the console.

    Console delivery means the repo works before you have configured anything. Switch to
    telegram/slack once the output is worth reading.

    `webhook` overrides SLACK_WEBHOOK_URL for this one send. Pass it when an employee has its
    own channel — muting one employee should never mean muting all of them.
    """
    channel = channel or env("BEADLE_CHANNEL", "console")
    if channel == "console":
        print(text)
        return "console"
    if channel == "telegram":
        return _deliver_telegram(text)
    if channel == "slack":
        return _deliver_slack(text, webhook)
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


def _deliver_slack(text, hook=None):
    hook = hook or env("SLACK_WEBHOOK_URL")
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


def probe(fn, unavailable=None):
    """Run one ground-truth probe. Never raises.

    A probe that dies must not take the consolidation down with it, and "could not verify" is
    itself an honest fact, much better than silently omitting the check, which reads to the
    model as "no problem here".
    """
    try:
        return fn()
    except Exception as e:
        return unavailable or "could not verify (%s)" % str(e)[:60]


def default_facts(emp):
    """Ground truth every employee gets for free, regardless of what it does.

    Each of these exists because memory drifted on it somewhere real:

    - **Delivery health.** An employee whose channel broke journals failures and nothing else,
      so "delivery is broken" persists in memory long after it is fixed. State the live answer.
    - **The action rate.** The employee's own effect, from claims.jsonl. Memory is otherwise
      happy to describe a stream of ignored output as productive work.
    - **Its own last runs.** A task erroring every run is the one thing an employee cannot see
      about itself: `LLM_ERROR` is journalled and then never mentioned again. This fact is what
      turns "I have been dead for eight days" into something the next consolidation must reckon
      with rather than quietly average out.
    """
    facts = [probe(lambda: "Now: " + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"))]

    def _delivery():
        ch = env("BEADLE_CHANNEL", "console")   # same resolution deliver() uses
        healthy = ("Delivery is HEALTHY right now (%s). DROP any memory thread claiming "
                   "delivery/auth is broken unless RECENT ACTIVITY shows a fresh failure.")
        if ch == "console":
            return "Delivery channel is console: nothing is actually being sent to a human yet."
        if ch == "telegram":
            tok = env("BEADLE_TELEGRAM_TOKEN") or env("TELEGRAM_TOKEN")
            if not tok:
                return "Delivery is MISCONFIGURED: channel is telegram but no token is set."
            u = (http_json("https://api.telegram.org/bot%s/getMe" % tok).get("result") or {}).get("username")
            return healthy % ("telegram, bot @%s reachable" % u)
        if ch == "slack":
            # A webhook cannot be probed without posting, so report configuration, not liveness.
            return ("Delivery channel is slack and a webhook IS configured."
                    if (env("SLACK_WEBHOOK_URL") or env("BEADLE_SLACK_WEBHOOK_URL"))
                    else "Delivery is MISCONFIGURED: channel is slack but no webhook is set.")
        return "Delivery channel is %s; not probed." % ch
    facts.append(probe(_delivery, "Delivery is FAILING right now: the channel did not answer."))

    def _claims():
        rows, _ = claims_due(emp, after_hours=0)
        if not rows:
            return ("This employee has made 0 claims, so it has NO measured action rate yet. Do not "
                    "describe its work as effective or ignored; there is no evidence either way.")
        checked = [r for r in rows if r.get("outcome") is not None]
        if not checked:
            return ("Claims RIGHT NOW: %d total, NONE reconciled yet. The action rate is UNKNOWN, "
                    "which is not the same as good. Do not describe this employee as effective."
                    % len(rows))
        # Report the buckets, not one number. "Acted on" and "got the outcome we wanted" are
        # different questions and a single rate silently answers whichever one you were not asking:
        # a closed-unmerged PR is a human acting, and is also the work being thrown away.
        buckets = {}
        for r in checked:
            buckets[str(r["outcome"])] = buckets.get(str(r["outcome"]), 0) + 1
        acted = sum(n for o, n in buckets.items() if o not in ("still_open", "ignored"))
        return ("Claims RIGHT NOW: %d total, %d awaiting reconcile, %d resolved (%s). A human acted "
                "on %d of %d resolved (%d%%). Use THESE numbers and correct any memory item "
                "claiming different ones; if memory quotes a success rate that is not one of these "
                "buckets, it is a different metric and must say which."
                % (len(rows), len(rows) - len(checked), len(checked),
                   ", ".join("%s %d" % (o, n) for o, n in sorted(buckets.items())),
                   acted, len(checked), round(100 * acted / len(checked))))
    facts.append(probe(_claims))

    def _self():
        p = os.path.join(emp_dir(emp), "journal.jsonl")
        if not os.path.exists(p):
            return "This employee has never journalled a run."
        last = {}
        for ln in open(p):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            last[r.get("task", "?")] = r
        # A broken run reaches the journal in more than one shape: bare "LLM_ERROR: ..." straight
        # from llm(), or wrapped by the task ("skipped — LLM_ERROR: ..."). Match the marker
        # anywhere in the summary rather than at the front, so a task that words its own prefix
        # differently is still caught. This is the fact that would have surfaced a fleet sitting
        # dead for eight days on a missing CLI, so it should not hinge on a string prefix.
        broken = [t for t, r in last.items() if "LLM_ERROR" in str(r.get("summary", ""))]
        if broken:
            return ("These tasks are BROKEN on their most recent run: %s. This is an outage of the "
                    "employee itself, not a quiet period. Open a thread for it and do not report "
                    "the employee as healthy." % ", ".join(sorted(broken)))
        return ("Every task's most recent run produced real output (%s). DROP any memory thread "
                "claiming a task is persistently failing." % ", ".join(sorted(last)))
    facts.append(probe(_self))

    return facts


def ground_facts(emp):
    """default_facts plus whatever employees/<emp>/facts.py adds.

    Convention: that file defines `facts()` returning a list of plain strings. Employee-specific
    truth is the whole point: the generic probes cannot know that this employee's memory keeps
    inventing a PR count or a queue depth.

    Phrase a fact as an INSTRUCTION, not a datum. "Open PRs: 2" invites the model to keep its
    own number alongside yours; "Open PRs RIGHT NOW: 2. Correct any memory item claiming a
    different count" is what actually overwrites the drift.
    """
    out = default_facts(emp)
    path = os.path.join(emp_dir(emp), "facts.py")
    if os.path.exists(path):
        def _load():
            spec = importlib.util.spec_from_file_location("facts_%s" % _slug(emp), path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return list(mod.facts())
        got = probe(_load, None)
        out.extend(got if isinstance(got, list) else ["employee facts.py failed: %s" % got])
    return "\n".join("- " + str(f) for f in out)


def consolidate(emp, facts=None):
    """Re-curate memory.md from the journal. Run it weekly, not every task.

    `facts` is deterministic live ground truth. Left as None it calls ground_facts(emp), which
    is what you want: memory drifts, and the fix is to hand it something authoritative to
    correct itself against, not a better prompt. Pass a string to override, or "" for none.
    """
    if facts is None:
        facts = ground_facts(emp)
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
    surprise on a laptop. Turn it on with BEADLE_GIT_COMMIT=1 once the employee lives on a box
    where nothing else writes to the checkout.
    """
    if env("BEADLE_GIT_COMMIT", "0") not in ("1", "true", "yes"):
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
