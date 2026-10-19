# Level M brief template

Written by the conductor at step 2, shown to the user (no wait for approval), passed to the executor verbatim and put into
the PR body. In English (it is a repository artifact); the conductor summarises it to the user in
their language.

```markdown
## Brief: <feature in one sentence>

**Level:** M — <why not S (e.g. 5 files, the place had to be found)>; <why not L (one side, no
money/auth/user data/migrations, no contract change)>.
**Side:** backend | frontend
**Branch:** feat/<slug>

### Goal
<two or three sentences: what the user can do after this that they cannot do now>

### Acceptance criteria
- [ ] **A1** Open <X> → do <Y> → expect <Z>
- [ ] **A2** <error / empty / edge case in the same form>

### Places to change
- `<path>` — <what changes>
- `<path>` — <what changes>

### Out of scope
- <what the executor must not do, even if it looks related>

### Tests
<which criteria get which test (unit / feature / e2e), or "Demo mode: no new tests">

### Risks and notes
<anything the executor should watch for; "none" is fine>
```
