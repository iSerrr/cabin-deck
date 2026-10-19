---
name: deliver
description: Build one or more approved specs end to end — parallel server/overlay executors in worktrees, gates, independent review, fix rounds — and open one PR per spec. Use when the user writes /deliver <id> [<id> ...], or asks to build, implement or "hand to the agents" approved specs.
---

# /deliver <id> [<id> …]

You (the main session) prepare inputs, run the `deliver` workflow, then integrate and publish. The
workflow does the building and reviewing; it never pushes or opens PRs. You do that.

## 1. Preflight: refuse early rather than fail late

For each `<id>`:

- `docs/specs/<id>-*/spec.md` exists **on `main`** with `status: approved`.
- Every `depends_on` spec has `status: done` on `main`, or is in this same batch **and** this spec
  touches only the overlay (the overlay builds against the contract, not the server code).
  Otherwise drop it from the batch and say why.
- Read `touches` from the front matter.
- Specs in one batch must touch disjoint files (e.g. one server-only and one overlay-only spec).
  Specs that share UI files go one at a time, each from `main` after the previous one merged.

For the environment:

- The working tree is clean, on `main`, and equal to `origin/main` (`git fetch` first).
- There is enough disk, and the main checkout has `.venv/` and `overlay/node_modules/` (worktrees
  reuse the latter through `scripts/worktree-init`), and `scripts/gates` passes on `main`.
- No stale worktrees from an interrupted run: `git worktree list`; if a side branch
  `feat/<id>-<side>` already exists, keep it — the workflow resumes from it.

Tell the user what will run: N specs, M sides, up to 1 + 2×maxFixRounds agents per side. Wait for a
yes if the batch has more than 3 specs. Otherwise proceed.

## 2. Run the workflow

Call the Workflow tool with `name: "deliver"` and:

```json
{ "base": "main", "maxFixRounds": 1, "specs": [ { "id": "E1.1", "dir": "docs/specs/E1.1-control-console", "touches": ["server", "overlay"] } ] }
```

Use `"maxFixRounds": 1` in Demo mode or early phases (one review round is the norm there).

It runs in the background and its completion wakes you. Do not poll it. Its result: `units[]` with
`outcome` = `approved` | `blocked` | `needs-human` | `failed` per side, plus the final review.

## 3. Integrate each spec

For each spec, in a fresh worktree so the user's checkout is untouched:

```bash
git worktree add .worktrees/<id> -b feat/<id>-<slug> origin/main
git -C .worktrees/<id> merge --no-ff feat/<id>-server  -m "feat: merge <id> server"     # if touched
git -C .worktrees/<id> merge --no-ff feat/<id>-overlay -m "feat: merge <id> overlay"    # if touched
```

Both sides touch disjoint directories, so a conflict means a side broke its boundary. Abort the
merge, do not resolve it, and report it.

Then, in that worktree, run `scripts/worktree-init` and `scripts/gates` on the merged result, and:

- write `docs/specs/<id>-<slug>/review.md`: per side, the outcome, `**Review rounds:** N`, the final
  verdict and `**Score:** N/10` (both read by `scripts/build-report.py`), every remaining finding
  (minor ones included), deviations and blocked reasons. Copy the reviewer's text; never soften it;
- if **every** touched side is `approved`, set `status: done` in `spec.md` and add the spec to
  "Done" in `docs/status.md`. Otherwise leave the status and add it to "Blocked / needs human";
- commit (`docs(spec): review report for <id>` plus the `Co-Authored-By` line).

## 4. Publish

Push `feat/<id>-<slug>` and open a PR titled `feat: <id> <title>`:

- all sides approved → a ready PR;
- any side `blocked`, `needs-human` or `failed` → a **draft** PR, with the blocking findings at the
  top of the body.

PR body: link to the spec, what was built per side, gate results, deviations, the steps the owner
runs on the Windows PC, then the review report. End with the PR attribution line from the system reminder.

Merge only if the root `CLAUDE.md` operating mode allows the main session to merge this kind of PR.
The project has no CI: the gates you ran on the merged result stand in for it, and the owner's check
on the Windows PC (the steps in the PR body) is part of gate two. Run `gh pr merge <n>` as a single
command, not chained with others. Never end a turn "waiting" without a PR monitor running.

## 5. Clean up and report

- Before removing any worktree that holds uncommitted work, save it as a `wip` commit on its side
  branch. Never `--force` remove first.
- `git worktree remove .worktrees/<id>` once pushed, then `git worktree prune`. Delete the local side
  branches only after the spec branch is pushed.
- Tell the user in their language: one line per spec with the PR link and its outcome, then what
  needs their decision (blocked reasons, needs-human findings, contract disagreements).
