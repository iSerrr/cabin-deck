---
module: ship
version: 1.0.0
status: implemented
---

# Ship — from a merged PR to a checked stage

A shared module: levels call it after their PR merges, instead of each describing the deploy.
Reference it as `uses: ship@1`. The conductor runs it; no agent builds or deploys by hand. Building,
deploying, the post-deploy smoke and the automatic rollback are the **pipeline's** job (CI and the
deploy workflow, `BLUEPRINT.md` §9–10). The conductor waits for the pipeline, reads its result and
reports.

## Inputs

From the root `CLAUDE.md`, section "Levels" → "Ship":

- **Deploy workflow**: the workflow that deploys `main` to stage (e.g. `stage`), or `none`.
- **Stage URL**: where the user smoke-tests, or `none`.

If either is a `<placeholder>`, treat it as `none` and say so in the report.

## When it starts

After the PR merges:

- **Autonomy B**: the conductor merged it itself; ship starts at once.
- **Owner-gated**: the level's report goes out at the PR (status "waiting for your merge"); ship
  starts when the merge happens (a PR monitor wakes the session, or the user says it is merged) and
  ends with a short ship update in the same report form.

## Steps

1. **Wait for the deploy.** Take the merge commit (`git rev-parse origin/main` after a fetch). Wait
   in the background for CI on `main` and then the deploy run for that commit
   (`gh run list --workflow <deploy> --commit <sha>`, then `gh run watch <id> --exit-status` as a
   background command, so its completion wakes the session). Never a bare wait, never polling in a
   loop. If CI on `main` fails, or no deploy run appears within 15 minutes of green CI, that is red.
2. **Read the post-deploy smoke.** Green means all three: the run concluded `success`; its smoke step
   passed; no rollback ran. Check the step log (`gh run view <id> --log`), not only the conclusion:
   a deploy that rolled back can still end green.
3. **Report with the stage link.** Write the level's smoke steps against the stage URL ("Open
   `<stage>/catalog` → …") and put the URL and the deploy run link in the report.
4. **On red, stop and report.** Which step failed (CI on `main`, build, deploy, smoke), the run log
   link, and whether the pipeline rolled stage back (stage is then on the previous release). Do not
   fix it inside this task, do not re-run or re-dispatch the deploy, do not redeploy older tags by
   hand. A fix is a new task and goes through the [router](../router.md); a manual rollback or
   re-run is the user's decision.

## Never

- Deploy to **production** as part of ship. Production goes only on the user's explicit command, and
  only through its workflow.
- Deploy by hand: no SSH, no `docker compose` on a server, no copying files. Only the pipeline.

## Without a pipeline

Deploy workflow `none`: ship ends at the merge. The report says "merged, no deploy pipeline", and the
smoke steps are written for a local run or wherever the user tests.

## Batches

When several PRs merge in a row (an S batch, several M tasks), ship the **last** merge commit and
check that the deployed commit contains all of them (`git merge-base --is-ancestor <each> <deployed>`):
the deploy workflow may skip intermediate commits. One ship result goes into the batch report.
