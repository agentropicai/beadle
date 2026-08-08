# Choosing your first employee

Read this before you write any code. Almost everyone who fails at this fails here, on scope,
not on technology.

## The rubric

A good first employee scores **yes on all six**. Five out of six means pick something else and
come back to this one third.

1. **It is a recurring decision someone already makes, on data you already have.**
   Not a new capability. If nobody is doing this today, you are building a product, not hiring
   an employee, and you should validate it the way you validate products.

2. **The data is deterministically fetchable.** A SQL query, an API call, a `gh` invocation. If
   step one needs scraping, OCR, or a login flow that breaks weekly, that is a separate project
   with its own risk. Do it second.

3. **There is a named human who receives the output and will act on it.** Name them. If you
   cannot, you are about to build something that runs perfectly and changes nothing.

4. **A wrong answer is cheap and reversible.** Your first employee will be wrong. Choose a place
   where that is embarrassing rather than expensive.

5. **It runs on a schedule, not on demand.** A schedule means there is no product surface to
   build — no UI, no auth, no latency budget. On-demand means you are building software.

6. **You can state the ground truth for last week's answer.** If you cannot grade it, you cannot
   improve it, and you will not be able to tell in month three whether it is working.

## Write it as one line

> **`<Role>` watches `<data>`, every `<cadence>`, and tells `<person>` `<what>`.**

Examples that pass:

- *Support Watch reads the ticket table every hour and tells Priya which conversations have
  gone unanswered past four hours and look genuinely stuck.*
- *Collections Associate reads the invoice ledger every Monday and tells Finance which overdue
  accounts changed status this week and which need a call today.*
- *Release Nag reads open PRs daily and tells the eng channel which tested branches nobody has
  merged, escalating by age.*

Examples that fail, and why:

- *"An agent that handles sales."* — no data, no cadence, no recipient, not a decision. Fails
  1, 3, 5, 6.
- *"A customer-facing support chatbot."* — on demand, customer-visible, wrong answers are
  expensive. Fails 4 and 5. This is the single most common first choice and the single worst.
- *"An agent that reads our Notion and answers questions."* — no recurring decision, no
  recipient, no ground truth. Fails 1, 3, 6.
- *"An agent that auto-fixes production incidents."* — irreversible. Fails 4. Build the one
  that *reports* incidents, run it for two months, then talk about acting.

## The first week

In this order. The order is the advice.

- **Day 1 — write `role.md`.** Then run the judge prompt by hand in a terminal against a paste
  of real data. Look at the output. You have now tested the entire product for free, and you
  will usually discover the mandate was wrong.
- **Day 2 — script the GATHER step.** Keep the judge as a prompt string in the task file.
- **Day 3 — schedule it, deliver to a channel, and add the gate.** The gate is what makes it
  survivable. Run it against a normal day and confirm it says nothing.
- **Day 4 — journal and memory.** Feed `role.md` + `memory.md` + recent journal back in as
  context via `lib.ctx()`.
- **Week 2 — reconcile.** Go back and check whether anyone acted on last week's output. This is
  where you find out whether you built anything.

Do not add a second employee until the first one has been quiet-when-it-should-be for a full
week. Two noisy employees are not twice as useful; they are zero, because nobody reads either.
