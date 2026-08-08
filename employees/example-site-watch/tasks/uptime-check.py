#!/usr/bin/env python3
"""
site-watch — uptime + latency check.

GATHER  fetch each URL in BEADLE_SITES (deterministic; no model).
GATE    a URL is "bad" if it errored, returned >=500, or is SLOW_FACTOR x its own median
        baseline over at least MIN_SAMPLES samples. Nothing bad -> exit before any model call.
JUDGE   one-shot: REAL or NOISE, given the numbers and the employee's memory.
DELIVER only when the judge says REAL. Records a claim so `reconcile` can check it later.

READ-ONLY: HTTP GET only.
"""
import sys, os, json, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import lib

EMP = "example-site-watch"
TASK = "uptime-check"

# --- thresholds, named and explained ----------------------------------------------------
SLOW_FACTOR = 3.0     # flag when a response takes >=3x this URL's own median
MIN_SAMPLES = 10      # never judge latency on a thin baseline; small n makes big percentages
KEEP_SAMPLES = 50     # rolling window per URL
BAD_STATUS = 500      # >= this is a server error; 4xx is usually us, not them

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(os.path.dirname(HERE), "baseline.json")

SITES = [s.strip() for s in lib.env("BEADLE_SITES", "https://example.com").split(",") if s.strip()]


# =======================================================================================
# 1. GATHER — deterministic
# =======================================================================================
base = json.load(open(BASELINE)) if os.path.exists(BASELINE) else {}
results = []

for url in SITES:
    status, elapsed, size, err = lib.http_status(url)
    samples = base.get(url, [])
    median = statistics.median(samples) if len(samples) >= MIN_SAMPLES else None
    results.append({"url": url, "status": status, "elapsed": round(elapsed, 3),
                    "bytes": size, "error": err, "median": median, "n": len(samples)})
    # Only healthy responses feed the baseline — otherwise an outage teaches the employee
    # that being broken is normal, and it stops alerting exactly when you need it to.
    if status and status < BAD_STATUS:
        base[url] = (samples + [round(elapsed, 3)])[-KEEP_SAMPLES:]

json.dump(base, open(BASELINE, "w"), indent=1)


# =======================================================================================
# 2. GATE — plain Python. Most runs end here, for free.
# =======================================================================================
def why_bad(r):
    """Returns (kind, description) or None.

    The kind matters more than it looks. A 500 or a DNS failure is a HARD fact — the check
    already proved it, and there is nothing left for a model to be skeptical about. Slowness
    is a SOFT signal — it is a comparison against a baseline, and comparisons are exactly
    where thin data produces confident nonsense.

    Handing both to the judge as one undifferentiated "is this real?" question is a mistake
    we shipped and had to fix: it dutifully applied the small-sample caveat to a hard 500 and
    suppressed a genuine outage. Give a judge only the question it can actually answer.
    """
    if r["error"]:
        return "hard", "unreachable: %s" % r["error"]
    if r["status"] >= BAD_STATUS:
        return "hard", "HTTP %d" % r["status"]
    if r["median"] and r["elapsed"] >= r["median"] * SLOW_FACTOR:
        return "soft", "slow: %.2fs vs median %.2fs (n=%d)" % (r["elapsed"], r["median"], r["n"])
    return None

bad = [(r, why_bad(r)) for r in results]
bad = [(r, k, w) for r, kw in bad if kw for k, w in [kw]]
hard = [b for b in bad if b[1] == "hard"]

# gate() records the decision either way, exits silently when nothing tripped, and occasionally
# lets a quiet run through to the judge anyway (GATE_SAMPLE) so we can see what we're missing.
mode = lib.gate(EMP, TASK, tripped=bool(bad),
                summary="%d site(s) healthy" % len(results) if not bad
                        else "%d/%d site(s) flagged" % (len(bad), len(results)))


# =======================================================================================
# 3. JUDGE — one call, tools off
# =======================================================================================
observed = bad if bad else [(r, "soft", "below threshold: %.2fs (median %s, n=%d)"
                                        % (r["elapsed"],
                                           ("%.2fs" % r["median"]) if r["median"] else "none yet",
                                           r["n"]))
                            for r in results]

facts = "\n".join("- [%s] %s -> %s (%.2fs, %s bytes; baseline median %s over n=%d)"
                  % (k.upper(), r["url"], w, r["elapsed"], r["bytes"],
                     ("%.2fs" % r["median"]) if r["median"] else "none yet", r["n"])
                  for r, k, w in observed)

prompt = lib.ctx(EMP) + (
    "\n\n=== TASK: uptime-check ===\n"
    "A deterministic check flagged the site(s) below. Two kinds of finding, and they are NOT "
    "judged the same way:\n"
    "  [HARD] — the site was unreachable or returned a 5xx. This is a MEASURED FACT, already "
    "proven by the check. Do NOT second-guess it and do NOT discount it for having a thin "
    "baseline; baseline size is irrelevant to a server error. Answer REAL unless the CURATED "
    "MEMORY above explicitly records that this exact URL is a known-accepted exception.\n"
    "  [SOFT] — a latency comparison against a baseline. Here skepticism is warranted: thin "
    "samples, a single slow request, or normal variance should be answered NOISE.\n"
    "If any HARD finding is present, the answer is REAL.\n"
    "Your FIRST line must be exactly one bare word, no markdown, no punctuation: REAL or NOISE.\n"
    "Then a blank line, then: if REAL, what is most likely wrong and the first thing a human "
    "should check; if NOISE, one line saying why.\n"
    "Output <=700 chars. End with a line: MEMORY: <one durable learning>\n\n"
    "=== DATA ===\n" + facts
)

verdict = lib.llm(prompt)
if lib.failed(verdict):
    lib.done(EMP, TASK, "skipped — " + verdict[:120], commit=False)
    sys.exit(0)

run_path = lib.save_run(EMP, TASK, verdict)


# =======================================================================================
# 4. DELIVER — gated on the verdict
# =======================================================================================
first_word = verdict.strip().lstrip("*_# ").upper()

if mode == "sample":
    # An audit run: the gate said nothing was wrong and we asked anyway. NEVER deliver these —
    # the point is to find out what the thresholds are hiding, not to route around them. If the
    # judge keeps saying REAL on sampled runs, your thresholds are too high.
    lib.done(EMP, TASK, "GATE AUDIT (below threshold, sampled): judge said %s. saved=%s"
             % (first_word.split()[0][:5] if first_word else "?", run_path), commit=False)
    sys.exit(0)

if first_word.startswith("NOISE"):
    status = "suppressed-noise"
else:
    status = lib.deliver("*site-watch — possible problem*\n\n" + verdict[:3500])
    for r, k, w in bad:
        lib.claim(EMP, key=r["url"], payload={"reason": w, "kind": k, "status": r["status"]})


# =======================================================================================
# 5. RECORD
# =======================================================================================
lib.done(EMP, TASK, "gate tripped on %d/%d site(s) (%d hard); verdict=%s delivery=%s saved=%s"
         % (len(bad), len(results), len(hard),
            first_word.split()[0][:5] if first_word else "?", status, run_path))
