# Orchestration levels

Development never runs without orchestration, but the amount of orchestration scales with the task.

| Level | For | Composition | Status |
| --- | --- | --- | --- |
| **S** | small changes in 1–3 files, obvious bugs, copy, config | the conductor alone, no sub-agents | `1.0.0` |
| **M** | a regular feature on one side | the conductor + 1 executor, sequentially | `1.0.0` |
| **L** | large modules, money, authorization, migrations | the conductor + architect, parallel executors per stage, a reviewer | `1.0.0` |

The **conductor** is the main session the user talks to.

## Layout

```
levels/
  README.md               this file: structure, versioning, how to add a level or an agent
  router.md               the single entry point: which level a task gets
  <level>/
    protocol.md           the level's protocol, `version` in the frontmatter
    templates/            reports and other fixed forms the protocol uses
    CHANGELOG.md          the level's own version history
  shared/
    <module>.md           a module several levels call (e.g. ship), `version` in the frontmatter
    CHANGELOG.md          one section per module
```

A level that is not implemented yet has only `README.md` with `status: not-implemented`; the router
then says "stop and ask the user" for it.

## Shared modules

A step that several levels do the same way lives once in `shared/` and is referenced like a level:
`uses: <module>@<major>`. A level links the module from its step instead of repeating it.

| Module | What | Version |
| --- | --- | --- |
| [`ship`](shared/ship.md) | after the merge: wait for the stage deploy, read its smoke, report with the stage link; stop on red | `1.0.0` |

## How it is used

1. Every task enters through [`router.md`](router.md), which picks the level.
2. The conductor announces the level and follows `<level>/protocol.md` step by step.
3. A protocol may escalate; escalation goes back through the router.

## Versioning

Each level and each shared module has its own [semver](https://semver.org/) version in the `version` field of its
`protocol.md` frontmatter, and a `CHANGELOG.md` entry for every version.

| Bump | When | Example |
| --- | --- | --- |
| **major** | the protocol's **behaviour** changes: steps added, removed or reordered, escalation triggers changed, what a step must do changed | `1.2.0 → 2.0.0` |
| **minor** | something is **added** without changing existing behaviour: a clarifying item, a template, a report field | `1.0.0 → 1.1.0` |
| **patch** | **wording** only, no change in behaviour | `1.1.0 → 1.1.1` |

A version is fixed once it reaches `main`. Until then (on a branch, in an open PR) the unreleased
version is edited in place, not bumped again.

The router has its own version on the same rules (its questions and its routing table are its
behaviour).

A level's version is independent of the canon version (`VERSION`, `.claude/orchestration-version`),
but a change to a level is also a change to the canon: bump the canon in the same PR per
`CONTRIBUTING.md` (a level major is a canon minor unless it breaks how existing projects run).

## Referring to a level

Refer to a level by name and **major** version: `level-s@1`. Any `1.x.y` satisfies `@1`; a major
bump means every reference has to be checked.

- **An agent** declares the levels it works under in its frontmatter and links the protocol instead
  of copying it:

  ```yaml
  ---
  name: <agent>
  description: …
  uses: level-m@1            # or a list: [level-m@1, level-l@1]
  ---
  ```

  ```markdown
  Follow the level M protocol (`.claude/levels/m/protocol.md`, `level-m@1`). In addition, for this
  agent: <only what is specific to this agent>.
  ```

- **The root `CLAUDE.md`** names the router and the levels the main session uses (section
  "Levels").

Rules for references:

- **Never copy a protocol's steps** into an agent, a skill or `CLAUDE.md`. Link it and add only what
  is specific to that place. If an addition is useful to every user of the level, it belongs in the
  protocol (a minor bump).
- An addition may narrow a protocol (an extra check, a stricter rule), never loosen it (skip a step,
  drop an escalation trigger).

## Adding a level

1. Create `levels/<name>/` with `protocol.md` (frontmatter `level`, `version: 1.0.0`,
   `status: implemented`), `templates/` if the protocol uses fixed forms, and `CHANGELOG.md` with the
   `1.0.0` entry. For a level that already has a stub, replace the stub `README.md` with these files.
2. Describe each step as an action, the escalation triggers, and what happens on escalation.
3. Add the level to the router's table and, if it changes which tasks go where, to its questions
   (a router major bump).
4. Update the status table at the top of this file and the canon `CHANGELOG.md`.

## Adding an agent that uses a level

1. Write the agent in `.claude/agents/<name>.md` as usual, with `uses: level-<x>@<major>` in the
   frontmatter.
2. In its body, link the protocol and write only the agent-specific additions (see above).
3. If the level's protocol names roles (e.g. "executor", "reviewer"), say which role the agent plays.

Example: `backend-dev` and `frontend-dev` (`uses: level-m@1`, role "executor"): one short section
"Level M: a brief instead of a spec" links the M protocol and adds only what differs from their spec
work; the rest of the agent (bootstrap, gates, commits) is shared by both uses. The fallback
[`../agents/executor.md`](../agents/executor.md) plays the same role in projects without side agents.

Models: set a model per role in the protocol (passed in the Agent call) when an agent serves several
levels, so one level's choice does not change another's; use the `model:` frontmatter field only for
an agent that serves one level (like `executor`).
