---
level: s
version: 1.0.0
status: implemented
---

# Level S — the conductor does it alone

For small changes: 1–3 files, an obvious bug, copy, styles, a config value. The main session (the
conductor) does the work itself, **without sub-agents**. The protocol is mandatory even for a
one-line change: every step below is done and visible to the user.

Reference it as `uses: level-s@1`.

## The five steps

### 1. Intake

Retell the task in **one sentence** and announce **"Level S"**. Ask no questions. If you need to ask
a question to understand the task, it is not S: go back to the [router](../router.md).

### 2. Locate

Find the file(s) and line(s) to change and name them (`path:line`). A few targeted searches at most;
if the place is not found, that is an escalation trigger (below).

### 3. Edit

Make the **minimal** change that does the task. No "while I'm here" fixes next to it: anything else
you notice goes into the report as a note, not into the diff.

### 4. Verify

Run the tests / gates of the side you touched (the commands in the project's side `CLAUDE.md`), and
CI on the PR.

- **Logic changed** (a validation, a condition, a calculation, a branch): add or update **one small
  test** that fails without the change and passes with it.
- **Copy, styles, config**: no new test; the existing gates must stay green.

If the project's `CLAUDE.md` is in **Demo mode**, Demo mode wins: no new tests, the remaining ones
stay green.

### 5. Deliver

Commit on a branch (`fix/<slug>` or `chore/<slug>`, per the project's Git rules), push and open the
PR the project's rules require; `main` still moves only through PRs. Merge per the project's mode,
then run [ship](../shared/ship.md) (`ship@1`): wait for the stage deploy, read its smoke, and report
to the user with [`templates/report.md`](templates/report.md), smoke steps against the stage URL.

## Escalation triggers

Stop as soon as one of these happens, and say **"this turned out to be M (or L), because …"**:

- the change spreads to **more than 3 files**;
- the place is not found after a few searches, or the **cause of the bug is not obvious**;
- the first edit **breaks tests and it is not clear why**;
- the change touches **payments, authorization, user data or migrations** → straight to **at least
  L**.

### What to do on escalation

1. Stop editing at S. Undo uncommitted edits made for this task; what you found (files, suspected
   cause) is input for the next level, not code to keep.
2. Tell the user: the level it turned out to be and which trigger fired.
3. Then, by level:
   - **M** — go on **at once** under the [M protocol](../m/protocol.md), from its step 1, without
     waiting for the user. What you found becomes the starting point of the brief.
   - **L** — go on at once under the [L protocol](../l/protocol.md), from its step 1. The user's
     gate there is the spec approval.

## Batch mode

A list of several S tasks is handled in **one session, one task at a time**:

- each task goes through all five steps and gets **its own commit** (on one batch branch, or one
  branch per task as the project's Git rules prefer);
- a task that escalates is set aside and the batch moves on to the next S task. After the S tasks,
  the tasks that turned out M are run under the M protocol one at a time (each with its own branch
  and PR), then those that turned out L go under the L protocol (their specs wait for the user's
  approval there);
- ship runs once, after the last merge of the batch;
- at the end: **one report** for the whole batch (the batch form in
  [`templates/report.md`](templates/report.md)) with a smoke checklist covering every task.
