# Level L report template

Sent to the user in **their** language: a short form after each stage, the full form after the
last one. Smoke steps come from the specs' acceptance criteria, written against the stage URL
([ship](../../shared/ship.md)).

```markdown
**Level L — <task in one sentence>** (<stage n of m | done>)

**Changed:** <two or three lines in plain language: what the user can do now>

| # | Stage | Spec PR | Delivery PR | Review (verdict, score per side) | Stage |
| --- | --- | --- | --- | --- | --- |
| 1 | <stage> | <link, approved> | <link, merged> | backend approve 8/10; frontend approve 9/10 | green |
| 2 | <stage> | <link, waiting for your approval> | — | — | — |

**Smoke (stage <URL>):**
- [ ] AC1. Open <X> → do <Y> → expect <Z>
- [ ] AC2. …

**Risk areas:** <for each touched area, one line: what was done (e.g. "migration is additive,
backfill 2 min on stage, reversible"; "every new route behind the manager role")>

**Production:** <what the production deploy needs (backup, migration lock time, order) — only on
your command | nothing special>

**Waiting for you:** <spec approvals, merges, decisions on blocked or needs-human findings, open
questions; "nothing">
```
