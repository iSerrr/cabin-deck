# Level M report template

The report goes to the user in **their** language. Smoke steps are the brief's acceptance criteria,
written for a person clicking through the product, against the stage URL when there is one
([ship](../../shared/ship.md)).

```markdown
**Level M — <feature in one sentence>**

**Changed:** <one or two lines in plain language: what the user can do now>

**Smoke:**
- [ ] A1. Open <X> → do <Y> → expect <Z>
- [ ] A2. …

**How it went:** executor <done | blocked>, fix rounds <0–2>; my check: scope <ok | note>,
criteria <n/n>, gates <green | red: which>.

**Tests / CI:** <tests added per criterion, or "Demo mode: no new tests">; CI <green | running |
red: link>. PR: <link> <(draft: open findings) if needs-human>

**Stage:** <green: <stage URL>, deploy <run link> | red: <failed step>, <log link>, <rolled back to
the previous release | not rolled back> | waiting for your merge | no deploy pipeline>

**Notes:** <deviations from the brief and why; things noticed but left out of scope; "none">
```
