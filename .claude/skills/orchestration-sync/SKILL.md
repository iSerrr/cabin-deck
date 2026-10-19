---
name: orchestration-sync
description: Keeps this project's agent setup in step with the orchestration canon repository — pull shows and applies canon changes newer than the pinned version through a PR in the project; push turns lessons learned here into a PR to the canon (LESSONS, BLUEPRINT, template). Use when the user writes /orchestration-sync [pull|push], says "sync the approach", "update the canon", "add a lesson to the canon", "синхронізуй підхід", "онови канон", "внеси урок в канон".
---

# /orchestration-sync [pull | push]

The canon is a separate repository (URL in the root `CLAUDE.md`, section "Orchestration canon";
default `https://github.com/iSerrr/agent-orchestration`). This project pins the canon version it
last synced with in `.claude/orchestration-version`. Without an argument, ask which direction, or
infer it from the user's words ("онови канон" / "add a lesson" → push; "sync the approach" → pull).

Ground rules for both directions:

- Work in a temporary directory for the canon clone (the session scratchpad, or `mktemp -d`), never
  inside the project tree.
- Never push to the canon's `main` or the project's `main`; both directions end in a PR.
- Never copy product code, secrets, keys, hostnames, IP addresses, emails, client names or client
  data into the canon. A real project may be named only as "a reference project (<name>)" in prose,
  and only if the owner agrees.
- Report to the owner in **their** language: what was pulled or pushed, and the PR links.

## pull — bring canon changes into this project

1. **Read the pin and the URL.** `pinned=$(cat .claude/orchestration-version)`; the canon URL from
   `CLAUDE.md`. If either is missing, ask the owner (the first sync of a project that copied the
   template by hand pins `0.0.0`).
2. **Fetch the canon.** `gh repo clone iSerrr/agent-orchestration "$tmp/canon"` (or `git clone`;
   `git -C "$tmp/canon" fetch --tags` if it already exists). Read `VERSION` = `latest`. If
   `latest == pinned`, say so and stop.
3. **Show what changed.** From `CHANGELOG.md`, the entries newer than `pinned`; from `LESSONS.md`, the
   entries added since (by date or by the changelog). Summarise them in a few lines.
4. **Diff the template against the project.** For each file under `"$tmp/canon/template/"` that the
   project also has at the same path (only files the project took from the template), run
   `git diff --no-index <project file> <canon template file>`. Files the project deliberately
   customised (gate commands, `<stack>` parts, the project half of `CLAUDE.md`) must keep the
   project's values: propose only the canon's generic changes. New template files the project does
   not have are listed as "new in the canon — take it?".
5. **Propose.** Show the owner a short list: file, what changes, why (link to the changelog or lesson
   entry), and your recommendation (take / adapt / skip). Wait for a yes, unless the root `CLAUDE.md`
   mode lets you apply process-only changes yourself.
6. **Apply on a branch.** `git switch -c chore/orchestration-sync-<latest> origin/main`, apply the
   agreed changes, write `<latest>` into `.claude/orchestration-version`, commit
   (`chore: sync orchestration canon to <latest>` plus the `Co-Authored-By` line), push, open a PR in
   the project whose body lists the changes and the skipped items with reasons. Merge per the mode.
7. **Tell the owner** (their language): from which version to which, what was taken, what was
   skipped, the PR link.

## push — contribute this project's lessons to the canon

1. **Collect candidate lessons** since the pinned version (`git log` since the commit that last
   changed `.claude/orchestration-version`):
   - this conversation: incidents, owner corrections, things that cost real time;
   - `CLAUDE.md` and `.claude/**` changes since the pin (`git diff <pin-commit> -- CLAUDE.md .claude`);
   - `docs/specs/*/review.md` and `state-*.md` findings about **process** (gates, reviews, contract
     handling, worktrees, CI, deploys), not about product behaviour;
   - a project `LESSONS.md` or `docs/status.md` "how each delivery is integrated" notes, if present.
2. **Keep only lessons about the approach.** A good lesson is reusable by a project with a different
   product and possibly a different stack. Drop product decisions, one-off bugs, and anything the
   canon already says (read `"$tmp/canon/LESSONS.md"` and `BLUEPRINT.md` first; if a lesson refines
   an existing one, update that entry rather than adding a duplicate).
3. **Generalise.** Rewrite each lesson as: date, source project (as the owner allows), what happened
   (2–3 sentences, no secrets, no hosts, no client data), the rule now (one imperative sentence).
   Where the rule changes how agents work, also prepare the change to `BLUEPRINT.md` and to the
   affected `template/` file. Show the owner the list and wait for a yes.
4. **Branch in the canon.** In `"$tmp/canon"`: `git switch -c lessons/<project>-<YYYY-MM-DD> origin/main`.
   Add the `LESSONS.md` entries (newest first), the `BLUEPRINT.md` and `template/` changes.
5. **Version.** Bump `VERSION` and add a `CHANGELOG.md` entry per `CONTRIBUTING.md`: **patch** for
   lessons and wording, **minor** for a new template piece or a new section/rule that projects should
   adopt, **major** for a change that breaks how existing projects run (renamed skills, workflow
   argument changes). Bump `template/.claude/orchestration-version` to the same value.
6. **Check before pushing.** `grep -rniE '<project-specific names, hosts, IPs, emails>'` over the diff
   returns nothing; every new internal link resolves; shell files pass `bash -n`.
7. **Open the PR in the canon.** Commit (`docs(lessons): <project> lessons <date>` plus the
   `Co-Authored-By` line), `git push -u origin lessons/<project>-<date>`, `gh pr create` with a body
   that lists each lesson in one line, the blueprint/template changes, and the version bump. Never
   merge it yourself unless the owner says so.
8. **Tell the owner** (their language): how many lessons, which rules changed, the new version, the
   PR link. After the canon PR merges, a later `pull` in this project moves its pin forward.
