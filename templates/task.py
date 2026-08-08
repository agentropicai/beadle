#!/usr/bin/env python3
"""
<employee> — <task name>.

<Two or three lines: what it gathers, what the gate is, what it delivers, and when it stays
silent. Write this before you write the code; if you cannot state the gate in one sentence,
you do not have one yet.>

READ-ONLY.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import lib

EMP = "<employee-folder-name>"
TASK = "<task-name>"

# --- thresholds live at the top, named, with a comment saying why -----------------------
# Do not bury these in the code. They are the part you will tune, they are the part that
# stops the employee being noise, and the comment explaining a past false alarm is worth
# more than the number itself.
THRESHOLD = 25          # flag when the metric is >=25% below baseline
MIN_ITEMS = 2           # one item moving is variance, not news
BASELINE_MIN = 20       # ignore anything below this — small numbers make big percentages


# =======================================================================================
# 1. GATHER — deterministic. No model. No exceptions.
# =======================================================================================
# rows = lib.sql("SELECT ...")
# data = lib.http_json("https://...")
# out  = lib.shell(["gh", "pr", "list", "--json", "number,title"])
rows = []


# =======================================================================================
# 2. GATE — perception. The most important lines in the file.
# =======================================================================================
# Decide *in plain Python* whether anything happened. If nothing did, lib.gate() exits here:
# no model call, no message, no cost. Most days, most employees should end on this line.
#
# When this task turns out to be noisy — and the first version always is — the fix goes
# HERE, not in the prompt. Tune the SQL before you tune the model.
#
# gate() returns "trip" (threshold crossed) or "sample" (it did NOT, but this run was randomly
# selected for audit — judge it, record it, deliver nothing). Every decision lands in gate.jsonl.
interesting = [r for r in rows if False]  # <-- your real condition

mode = lib.gate(EMP, TASK, tripped=len(interesting) >= MIN_ITEMS,
                summary="%d of %d rows crossed the threshold" % (len(interesting), len(rows)))


# =======================================================================================
# 3. JUDGE — one model call. Tools off. It sees only the data you hand it.
# =======================================================================================
# Two rules that make the output usable:
#   - Force a machine-readable first line, so DELIVER can gate on it without parsing prose.
#   - Give it an explicit way to say "this is nothing". A judge that cannot say no is a
#     rubber stamp, and you will stop reading its output within two weeks.
facts = "\n".join("- %s" % r for r in interesting)

prompt = lib.ctx(EMP) + (
    "\n\n=== TASK: %s ===\n" % TASK +
    "A deterministic check crossed its threshold. Decide whether this is REAL and worth a "
    "human's attention, or NOISE.\n"
    "Your FIRST line must be exactly one bare word, no markdown, no punctuation: REAL or NOISE.\n"
    "Then a blank line, then: if REAL, the likely cause and the first thing to check; "
    "if NOISE, one line saying why.\n"
    "Be conservative — false alarms erode trust faster than misses do. Output <=900 chars.\n\n"
    "=== DATA ===\n" + facts
)

verdict = lib.llm(prompt)
if lib.failed(verdict):
    # Never deliver an error to your team, and never fail silently either — journal it so
    # the fleet-health task can see this employee is broken.
    lib.done(EMP, TASK, "skipped — " + verdict[:120], commit=False)
    sys.exit(0)

run_path = lib.save_run(EMP, TASK, verdict)


# =======================================================================================
# 4. DELIVER — gated on the judge's verdict.
# =======================================================================================
first_word = verdict.strip().lstrip("*_# ").upper()

if mode == "sample":
    # Audit run: the gate said nothing happened and we asked anyway, to find out what the
    # thresholds are hiding. Never deliver these. If the judge keeps saying REAL here, your
    # thresholds are too high.
    lib.done(EMP, TASK, "GATE AUDIT (below threshold): judge said %s. saved=%s"
             % (first_word.split()[0][:5] if first_word else "?", run_path), commit=False)
    sys.exit(0)

if first_word.startswith("NOISE"):
    status = "suppressed-noise"
else:
    status = lib.deliver("*%s — %s*\n\n%s" % (EMP, TASK, verdict[:3500]))
    # If this claim is something a human is supposed to ACT on, record it so the reconcile
    # task can check later whether they did. See docs/05-the-outcome-loop.md.
    # lib.claim(EMP, key=..., payload={"detail": ...})


# =======================================================================================
# 5. RECORD
# =======================================================================================
lib.done(EMP, TASK, "gate tripped (%d items). delivery=%s saved=%s"
         % (len(interesting), status, run_path))
