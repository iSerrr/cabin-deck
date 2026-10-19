---
name: spec
description: Turn a backlog epic (e.g. E1.3) into a draft spec in docs/specs via the architect agent, and open a spec PR for approval. Use when the user writes /spec <id>, asks to "specify", "design" or "write the spec for" an epic, or wants the next epic prepared.
---

# /spec <id>

Produces `docs/specs/<id>-<slug>/` with `status: draft` on its own branch and PR. You (the main
session) orchestrate; the `architect` agent writes.

## 1. Check the ground

- `<id>` exists in `docs/backlog.md`. If the user gave no ID, propose the next unspecified epic in
  backlog order whose dependencies are `done`, and confirm it.
- No folder `docs/specs/<id>-*` exists on `main` or on an open `spec/<id>-*` branch. If one does,
  this is a revision: pass the existing spec and the requested changes to the architect instead.
- Every `depends_on` epic of `<id>` is at least `approved`. Otherwise say which one blocks it.
- The working tree is clean and on `main`, up to date with `origin/main`.
- Read the operating mode in the root `CLAUDE.md` (Demo mode means a short spec).

## 2. Branch

```
git switch -c spec/<id>-<slug> main
```

Everything below lands on this branch.

## 3. Run the architect

Spawn the `architect` agent (Agent tool, `subagent_type: architect`, foreground). In its prompt give
the epic ID and backlog line, anything the user said about it in this conversation, the branch name,
the operating mode, and a **size target with a cut line** (what must be in, what can move to a
follow-up). Ask for the summary described in its instructions.

## 4. Check the result yourself before anyone else sees it

Read `spec.md` and `tasks.md`. Send it back to the architect (SendMessage, same agent) if any of
these fail:

- every template section is present ("None" with a reason is fine; an empty section is not);
- every requirement has an ID, at least one acceptance criterion and one task;
- the contract is concrete enough to build the overlay against a fake server: every route, message
  and process interface typed, every status code with its body, and every route that controls the
  PC limited to `127.0.0.1`;
- "Risks and edge cases" answers the architect's Cab Deck checklist (buttons never stuck, Windows
  process cleanup, steps for the owner on the gaming PC);
- `touches` matches which sides `tasks.md` actually has tasks for;
- nothing contradicts `docs/architecture.md` without being called out;
- in Demo mode: acceptance is a click-through checklist and there are no test tasks.

## 5. Publish

Commit (`docs(spec): draft <id> <title>` plus the `Co-Authored-By` line), push the branch and open a
PR titled `spec: <id> <title>`. Body from the architect's summary: what the spec covers, what is out
of scope, and the open questions as a checklist. End with the PR attribution line from the system
reminder.

## 6. Tell the user

In the owner's language (see the root `CLAUDE.md`), briefly: the PR link, two or three lines on what
the spec decides, and the open questions that need their answer. Approving means setting
`status: approved` and merging. **Set `approved` or merge yourself only when the root `CLAUDE.md`
operating mode allows it for this kind of spec** (e.g. Autonomy B for low-risk phases); otherwise
never.
