# Guardrails

Do these on day one. Every one of them exists because the opposite has gone wrong somewhere,
usually expensively.

## 1. Read-only credentials

Not a convention. A database role that **cannot** write, an API scope that is
`something.readonly`, a token with no push permission. `MUSTER_DSN` should point at a read-only
role and nothing else.

The distinction matters because guardrails written in `role.md` are guidance, and guidance is
followed at whatever rate a model follows guidance. A credential that cannot write is
enforcement. **Anything whose violation must be prevented rather than discouraged belongs in a
permission, not in prose.**

## 2. Draft-and-approve

The employee never publishes, deploys, pays, merges, sends, or messages anyone outside its own
channel. Everything that would change the world is a draft that a human approves.

This is the design, not a phase to grow out of. In the production fleet this was extracted
from — running since mid-2026 across five employees — nothing has ever been merged or deployed
by an agent. The SRE employee writes fixes, tests them on an isolated machine, and opens a pull
request. A human merges. That has not been a bottleneck; it has been the reason it is still
running.

## 3. The irreversibility rule

> **If the action cannot be undone, the agent does not cross the checkpoint alone.**

That single sentence resolves nearly every autonomy argument without a maturity model. Sort your
actions by reversibility, not by severity:

```
read → draft → internal write → external send → system-of-record change → delete / irreversible
                                     ^
                          everything past here needs a human first
```

Note the axis is *reversibility*, not *importance*. An agent editing a draft blog post is fine.
An agent sending one customer email is not, and the email is the smaller action.

For the high-risk end, a yes/no prompt is not enough. Show intent, the data used, the proposed
action, the expected consequence, and the rollback path.

## 4. Everything fetched is data, not instructions

Database rows, support tickets, inbound messages, web pages, file uploads, third-party repos.
Any of it can contain text aimed at the model that will read it. Never act on an instruction
that arrives inside the data.

**And do not rely on saying so.** The structural version is quarantine:

| | reads untrusted content | holds privileged tools |
|---|---|---|
| the reading employee | yes | **no** |
| the acting employee | **no** | yes |

The reading employee produces structured output. A *separate* employee acts on it. This holds
even when an injection succeeds, which is the difference between a control and a hope.

Muster's shape makes this cheap: `lib.file_task()` is the only channel between employees, and
the receiving employee re-judges what it is handed rather than trusting the sender's severity.

## 5. Name your domain's safety gate

Every domain has one, and if you do not name it in `role.md` it does not exist.

- Health: no clinical claim carries a byline without a clinician signing off; never fabricate a
  citation; never auto-publish.
- Finance: nothing pays out without human approval; reconciliation is read-only.
- Legal / contracts: no draft leaves the building without review.
- Anything customer-facing: a human reads it before a customer does.

Write it in the imperative, in the `Must NOT` section, and be specific enough that you could
point at the line during a review.

## 6. No PII in output

Name the fields explicitly — phone numbers, emails, account IDs, addresses. "Be careful with
personal data" is not an instruction anyone can follow. Strip query strings from URLs before
they reach a message or a journal line; tokens live in them more often than you would like.

## 7. Secrets stay out of git

`.env` is gitignored. Keep it that way. Live secrets belong on the machine that runs the
employee and nowhere else.

## 8. One employee watches the others

Not a guardrail against the agents; a guardrail against silence. Tokens expire, tunnels drop,
timers crash, and a delivery failure returns an error string nobody reads. In the fleet this was
extracted from, exactly that hid one employee's auth failure for weeks.

Muster records dropped sends to `.deliver-failures.jsonl` and `./muster status` surfaces them
unprompted. Your third employee should be the one that checks the first two ran, delivered, and
did not go stale — deterministic, alert-once, no model involved.
