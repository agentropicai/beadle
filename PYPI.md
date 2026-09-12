# Beadle

**Build an AI employee without building an agent platform.**

Most of any job is *noticing*, not thinking — scanning, comparing against a baseline, concluding
nothing changed. Noticing is constant and answerable in SQL. Judgment is rare, expensive, and the
only part a model is good at. Most agent systems fuse the two and pay judgment prices for
noticing. Beadle keeps them apart.

```
pip install beadle
beadle init my-employees
cd my-employees
./beadle doctor
./beadle run example-site-watch uptime-check
```

Every task is the same five steps:

```
GATHER   deterministic — SQL, an API call, a shell command. No model.
GATE     plain Python. Did anything happen? If not, stop here — silently.
JUDGE    one isolated model call. It sees only the prompt produced by GATHER.
DELIVER  gated. Silence is the correct output most days.
RECORD   journal, archive.
```

There is no agent loop. On the production fleet this was extracted from — 21 live tasks —
10 never call a model at all, 18 can exit before the model is invoked, and the busiest task runs
144 times a day for zero tokens.

The judge uses a logged-in Claude Code or Codex CLI subscription, selected with
`BEADLE_LLM_PROVIDER=claude|codex`; an optional `BEADLE_LLM_FALLBACK` can use the other login on
auth or quota failure. No model API key is required.

Beadle is a workspace you own and edit. `beadle init` fetches it and gets out of the way. Full
docs, four working example employees, and a complete worked build (including the bug hit along
the way) are in the workspace itself.

## Or import it into a codebase you already have

If you already have a repo with scheduled scripts in it, you do not need a second workspace:

```python
from beadle import lib          # BEADLE_HOME=/path/to/your/repo
```

`BEADLE_HOME` decides where `.env`, `logs/` and employees live; `BEADLE_EMPLOYEES` overrides the
employee root on its own, so an existing layout keeps working (`lib.journal("teams/sre", ...)`)
without moving a single folder. Everything else is identical, because it is the same `lib.py`.

The workspace remains the recommended way in: reading the four example employees teaches the
shape faster than any API docs, and editing your own copy of `lib.py` is a feature, not a
violation. Import it when you have an existing fleet to fold in rather than a new one to start.

MIT · https://github.com/agentropicai/beadle
