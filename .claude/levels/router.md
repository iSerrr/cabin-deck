---
name: router
version: 1.0.0
---

# Level router

The single entry point for every development task. Development never runs without orchestration;
the router decides **how much** orchestration a task gets. The main session (the conductor) routes
each task before it touches anything, says the level out loud, then follows that level's protocol.

## The three questions

Answer them in order, from the task as given and a quick look at the code (no edits yet).

1. **Can the task be retold in one sentence, and is the place to change already known (1–3 files)?**
   Yes → **S**, unless question 2 is also yes. No → go to 2.
2. **Does it touch money (payments, prices, invoices), user data, authorization or migrations?**
   Yes → **L**, whatever the answers to 1 and 3. No → go to 3.
3. **Does it need several stages or both sides (e.g. database + API + UI, a new or changed API
   contract, or work that has to be split and sequenced)?** Yes → **L**. No (one stage, one side)
   → **M**.

Question 2 is a veto: a one-line change to a payment amount, a permission check or a migration is
never S.

When in doubt between two levels, take the higher one.

## Where each level goes

| Level | Protocol | Status |
| --- | --- | --- |
| **S** | [`s/protocol.md`](s/protocol.md) (`level-s@1`) | implemented |
| **M** | [`m/protocol.md`](m/protocol.md) (`level-m@1`) | implemented |
| **L** | [`l/protocol.md`](l/protocol.md) (`level-l@1`) | implemented |

Never quietly downgrade a task. A protocol may move a task down only where it says so, with the
reason stated.

## Changing the level mid-task

A level's protocol can escalate (S and M list their triggers). Say "this turned out to be <level>,
because …" and continue **at once** under the new level's protocol, from its step 1, without waiting
for the user. The user's gates are inside the protocols (at L: the spec approval), not at the switch.
L is the top level: its protocol says when it stops.
