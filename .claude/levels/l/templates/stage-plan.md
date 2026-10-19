# Level L stage plan template

Written by the conductor at step 2 and shown to the user in their language (no wait for approval:
the gate is the spec). The English version goes into the first spec PR's body.

```markdown
## Stage plan: <task in one sentence>

**Level:** L — <router question or escalation trigger that put it here>
**Starting point:** <what exists today; what S or M already found or built, with branches>

| # | Backlog ID | Stage (one line) | Sides | Depends on | Risk areas |
| --- | --- | --- | --- | --- | --- |
| 1 | E2.4a | <data model and API for …> | backend, frontend | — | migrations, user data |
| 2 | E2.4b | <UI for …> | frontend | E2.4a | — |

**Gates:** each spec is approved by <you | me (Autonomy B, no risk areas)>; each delivery PR is merged
by <you | me>. Production: only on your command.

**Out of this task:** <what is deliberately left for later>
```
