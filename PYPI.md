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
JUDGE    one model call. Tools disabled, max-turns 1.
DELIVER  gated. Silence is the correct output most days.
RECORD   journal, archive.
```

There is no agent loop. On the production fleet this was extracted from — 21 live tasks —
10 never call a model at all, 18 can exit before the model is invoked, and the busiest task runs
144 times a day for zero tokens.

Beadle is a workspace you own and edit, not a library you import. `beadle init` fetches it and
gets out of the way. Full docs, four working example employees, and a complete worked build
(including the bug hit along the way) are in the workspace itself.

MIT · https://github.com/agentropicai/beadle
