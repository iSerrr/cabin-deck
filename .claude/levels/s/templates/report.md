# Level S report template

The report goes to the user in **their** language (the root `CLAUDE.md` names it). Keep it this
short. Smoke steps are written for a person clicking through the product, not for a developer, and
point at the stage URL when there is one ([ship](../../shared/ship.md)).

## Single task

```markdown
**Level S — <task in one sentence>**

**Changed:** <one line in plain language: what is different for the user>

**Smoke:**
- [ ] Open <X> → do <Y> → expect <Z>
- [ ] <optional second smoke, same form>

**Tests / CI:** <gates run and their result; new or updated test, or "no new test: copy/style/config">;
CI <green | running | red: link>. PR: <link>

**Stage:** <green: <stage URL>, deploy <run link> | red: <failed step>, <log link>, <rolled back to
the previous release | not rolled back> | waiting for your merge | no deploy pipeline>
```

## Batch

```markdown
**Level S, batch of <n> tasks**

| # | Task | Changed | Commit | Status |
| --- | --- | --- | --- | --- |
| 1 | <task> | <one line> | <short sha> | done |
| 2 | <task> | <one line> | PR <link> | escalated to M (<trigger>), delivered under M |
| 3 | <task> | — | — | escalated to L (<trigger>), spec PR <link> waiting for your approval |

**Smoke checklist:**
- [ ] 1. Open <X> → do <Y> → expect <Z>
- [ ] 1. <optional second smoke>
- [ ] 3. …

**Tests / CI:** <gates and result per task, or once for the batch>; CI <status>. PR: <link(s)>

**Stage:** <green: <stage URL>, deploy <run link> | red: <failed step>, <log link>, <rolled back to
the previous release | not rolled back> | waiting for your merge | no deploy pipeline>
(one deploy for the batch; it contains every merged task)

**Escalated:** <for each: level, trigger, what was found; M tasks link their M report, L tasks link
their stage plan and spec PR>
```
