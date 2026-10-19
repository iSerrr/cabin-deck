---
level: m
version: 1.0.0
status: implemented
---

# Level M — the conductor and one executor

For a regular feature: one stage, on **one side** (backend or frontend), with no API contract to
negotiate between sides and nothing from the router's veto list (money, authorization, user data,
migrations). The main session (the **conductor**) plans and checks; one **executor** sub-agent
writes the code. They work **sequentially**, never in parallel, and there is no separate reviewer:
the conductor checks the work itself.

| Role | Agent | Model |
| --- | --- | --- |
| conductor | the main session | the session's model |
| scout (optional) | built-in `Explore`, read-only | `haiku` |
| executor | `backend-dev` or `frontend-dev` for the brief's side; [`executor`](../../agents/executor.md) only in projects without side agents | `sonnet` |

Reference it as `uses: level-m@1`.

## The five steps

### 1. Intake

Retell the task in one or two sentences and announce **"Level M"** with the router's reason (why not
S, why not L). Questions are allowed here, **once**, all in one message, and only those whose answer
changes what gets built. If the answers move the task to L, escalate (below).

### 2. Plan (the brief)

Read the code the feature touches. On a large codebase, send the built-in `Explore` agent (Agent
tool, `subagent_type: "Explore"`, `model: "haiku"`) with a precise question ("where is the catalog
sort built, and which files would a new sort option touch?") instead of reading everything yourself;
it only reads. You still check the places it names and write the brief yourself. Then write a brief from [`templates/brief.md`](templates/brief.md):
goal, side, acceptance criteria as smoke steps, the places to change (`path` + what), out of scope,
the tests expected, risks. The brief is what the executor builds against and what you check against;
it replaces a spec at this level.

**Show it and go on.** Post the brief to the user (a short summary in their language) and go
straight to step 3, in every mode: there is no wait for approval. If the user corrects the brief
later, update it and pass the change to the executor (as a fix round if it has already reported).
The brief also goes into the PR. If writing the brief needs an architectural decision, that is an
escalation trigger, not something to decide here.

### 3. Execute

Spawn **one** executor in its own worktree (Agent tool, `isolation: "worktree"`, `model: "sonnet"`):
`backend-dev` or `frontend-dev` for the brief's side, or `executor` in a project without side agents.
Give it: "Level M: a brief instead of a spec", the brief verbatim, the side, the base (`main`), and
the branch name `feat/<slug>`. The model is set in the call, not in the side agents' files, so
`/deliver` keeps running them on its own model. The executor bootstraps the
worktree, builds, runs its side's gates, commits, and returns a report with `status: done | blocked`.

You do not write product code at this level. While the executor runs, you wait for its completion
notification; do not poll it.

### 4. Check

You are the reviewer at this level. On the executor's branch:

- **Scope:** `git diff main...feat/<slug> --stat` touches only the brief's side and places; nothing
  outside it, no new dependency, no migration.
- **Criteria:** every acceptance criterion is implemented (read the code, not only the report).
  Outside Demo mode, each criterion with logic has a test that fails without the change.
- **Gates:** re-run the side's gates once yourself in the executor's worktree (the commands are in
  the side's dev agent, section "Gates", or in `CLAUDE.md` for a project without side agents). A failing gate is a finding, whatever the report says.
- **Triggers:** none of the escalation triggers below fired during the work.

Findings go back to the executor as a list (file, line, what is wrong, the fix): continue the same
agent, or spawn the same executor agent again on the same branch (it resumes). At most **2 fix rounds**. If the
work is still not right after them, stop: open a **draft** PR with the open findings and tell the
user (needs-human).

### 5. Deliver

Push `feat/<slug>`, open a PR whose body has the brief, the executor's summary, your check (gates,
criteria, fix rounds) and the reasons for any deviation. Wait for CI (a background poll or a PR
monitor, never a bare wait). Merge per the project's mode, then run [ship](../shared/ship.md)
(`ship@1`): wait for the stage deploy, read its smoke, and report to the user with
[`templates/report.md`](templates/report.md), smoke steps against the stage URL. A red deploy stops
the task there; the fix is a new task.

## Tests

Outside Demo mode: every acceptance criterion that involves logic has a test (unit, feature or e2e,
per the side's rules) that fails without the change; copy, styles and config need none. In Demo
mode: no new tests, the remaining ones stay green.

## Escalation triggers

Stop as soon as one of these happens, and say **"this turned out to be L, because …"**:

- the feature touches **payments, authorization, user data or migrations**;
- it needs **both sides**, or a new or changed API contract between them;
- it needs **several stages** (e.g. data model, then API, then UI), or the brief cannot be written
  without an **architectural decision**;
- the executor reports **blocked** on something the brief cannot answer, or its diff has to grow
  well past the places listed in the brief.

On escalation, continue at once under the [L protocol](../l/protocol.md) (below). Going down is allowed once, at
the plan step: if reading the code shows the task is a 1–3 file change
with a known place, say "this is S, because …" and continue under the S protocol.

### What to do on escalation

1. Stop the M work: spawn nothing more; leave the executor's branch as it is (do not delete
   committed work) and do not open its PR.
2. Tell the user: "this turned out to be L, because …", and what was found or built so far (branch,
   files).
3. Continue at once under the [L protocol](../l/protocol.md), from its step 1, with the brief and the
   branch as its starting point. The user's gate there is the spec approval.

## Several M tasks

One at a time: each task goes through all five steps with its own branch and PR. The next one starts
after the previous PR is open (not necessarily merged), from `main`, unless it depends on the previous
one; then it waits for the merge.
