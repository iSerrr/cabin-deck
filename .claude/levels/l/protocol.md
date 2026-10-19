---
level: l
version: 1.0.0
status: implemented
---

# Level L — stages, specs, parallel executors and a reviewer

For large modules, money, authorization, user data, migrations, anything that needs both sides with
an API contract, or several stages. The main session (the **conductor**) splits the work into
stages and runs each stage through the spec → deliver flow that already exists in this setup:
[`/spec`](../../skills/spec/SKILL.md) and [`/deliver`](../../skills/deliver/SKILL.md). This protocol
says how the conductor uses them at level L; it does not repeat them.

Reference it as `uses: level-l@1`.

| Role | Agent | What it does |
| --- | --- | --- |
| conductor | the main session | intake, stage plan, checks, integration, PRs, ship, reports |
| scout (optional) | built-in `Explore`, `haiku` | finds what exists before the stage plan |
| designer (optional) | `designer` | caches design frames for UI stages, through `/design` |
| architect | `architect` | one spec per stage, through `/spec` |
| executors | `backend-dev`, `frontend-dev` | build the sides of a stage **in parallel**, each in its worktree, through `/deliver` |
| reviewer | `reviewer` | independent review of each side, verdict + score, through `/deliver` |

## Before the first L task

The project needs `docs/architecture.md` and `docs/backlog.md` (`BLUEPRINT.md` §15). If either is
missing, stop: say so and offer to write them with the user first. Specs cannot be designed without
them.

## The six steps

### 1. Intake

Retell the task in two or three sentences and announce **"Level L"** with what put it here: the
router question that decided it, or the trigger that escalated it from S or M (and what that level
already found or built: files, branches). Questions are allowed, once, all in one message, only those
that change the stage plan.

### 2. Stage plan

Split the task into **stages**. A stage is one spec that can be delivered in **one PR per side**:
both sides of one stage build in parallel against that spec's contract. Stages that need the previous
one merged (a data model before the features on it, an API before a second UI that needs it live)
are separate specs chained with `depends_on`. Prefer fewer, smaller stages; split when one spec would
not fit one PR per side.

Write the plan from [`templates/stage-plan.md`](templates/stage-plan.md): stages in order, for each the
backlog ID, scope in one line, sides, `depends_on`, and which risk areas it touches (below). Tasks
that are not in `docs/backlog.md` get an entry there (an ID such as `E2.4`, or `E2.4a`, `E2.4b` for
stages), committed on the first stage's spec branch.

**Show it and go on.** Post the plan to the user in their language and go on to step 3: the user's
gate at this level is the spec (step 3), not the plan. If reading the code shows the whole task is
one side, no contract and nothing from the risk areas, say "this is M, because …" and continue under
the [M protocol](../m/protocol.md). A task that touches a risk area never goes down.

### 3. Spec (gate one)

For the next stage whose `depends_on` are done, run `/spec <id>`. In the architect's prompt, besides
what `/spec` passes, include the stage's scope line, the cut line, and the **risk checklist** for
every risk area the stage touches. Before publishing, check that the spec's "Risks and edge cases"
answers every item of it, in addition to the checks in `/spec`.

The spec PR is gate one. **Owner-gated** mode: the user approves (sets `status: approved`, merges),
and a spec that touches a risk area is **always** approved by the user, whatever the mode.
**Autonomy B**: the conductor may approve specs that touch no risk area. While a spec waits for
approval, report and keep something that will wake the session (a PR monitor); do not start the
delivery.

### 4. Deliver

Run `/deliver <id>` for the approved stage: one executor per side in its own worktree, in parallel,
each side reviewed by the `reviewer`, fix rounds up to `maxFixRounds` (2; 1 in Demo mode). `/deliver`
integrates the sides and opens the PR, a **draft** if a side ends `blocked`, `needs-human` or `failed`.

Independent stages (no `depends_on` between them, disjoint files) may go in one `/deliver` batch, as
`/deliver` allows. Dependent stages wait for the previous stage to be merged and shipped.

### 5. Merge and ship (gate two)

The delivery PR merges on green CI: by the user in Owner-gated mode, and by the user for any stage
that touches a risk area; by the conductor in Autonomy B for the others, only with reviewer `approve`
on every side. Then run [ship](../shared/ship.md) (`ship@1`). For a stage with a migration, also
read the migration step in the deploy log, and list in the report what production will need (backup
first, how long the migration may lock, whether it is reversible). Production stays the user's
command.

### 6. Next stage

When the stage ships green, go back to step 3 for the next one. After the last stage, send the final
report from [`templates/report.md`](templates/report.md). Between stages, send a short stage report
in the same form so the user sees progress.

## Risk checklist

The architect answers each item for every risk area the stage touches; the reviewer checks them
(its "Correctness" and "Security" steps already cover them, the spec makes them explicit).

- **Money:** amounts in integer minor units with the currency; rounding rule and where it happens;
  idempotency of payment callbacks and retries; refunds and partial states; what the user sees when
  a payment fails halfway.
- **Authorization:** the guard of every new or changed route and admin action; who may do what (a
  role table); what a user without the right sees (403 vs 404).
- **User data:** isolation between users or tenants; which personal fields are added, where they are
  shown, logged or exported; retention and deletion.
- **Migrations:** additive where possible; a down path or why there is none; backfill of existing
  rows and how long it takes; locks on large tables; never editing a migration already on `main`;
  the order of deploy (migration before the code that needs it).

## When to stop

L is the top level, so nothing escalates further. Stop, report and wait for the user when:

- the spec needs an architectural decision that `docs/architecture.md` does not cover or contradicts:
  the architect proposes it (an ADR draft in `docs/decisions/`), the user decides;
- a delivery ends with a side `blocked`, `needs-human` or `failed` (the draft PR carries the reasons);
- an executor finds the contract wrong or impossible: the spec is revised through `/spec` (back to
  step 3), never changed on the fly;
- ship is red: the fix is a new task and goes through the [router](../router.md).

The other stages wait until the stopped one is resolved, unless they do not depend on it.
