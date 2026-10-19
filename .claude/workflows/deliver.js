export const meta = {
  name: 'deliver',
  description: 'Build approved specs: each side in its own worktree, gated, reviewed, fixed until approved',
  whenToUse: 'Run by the /deliver skill with approved specs from docs/specs; not for ad-hoc changes',
  phases: [
    { title: 'Implement', detail: 'executor per spec side (server / overlay), isolated worktrees' },
    { title: 'Review', detail: 'reviewer re-runs gates and checks spec + contract' },
    { title: 'Fix', detail: 'developer addresses review findings' },
  ],
}

// args: { base: 'main', maxFixRounds: 2, specs: [{ id: 'E1.1', dir: 'docs/specs/E1.1-control-console', touches: ['server', 'overlay'] }] }
// Cab Deck: the sides are `server` and `overlay`, their paths are listed in the root CLAUDE.md (section "Sides").
// Every side is built by the `executor` agent and reviewed by `reviewer`.
// Pass maxFixRounds: 1 in Demo mode or early phases: one review round is the norm there.
const BASE = (args && args.base) || 'main'
const MAX_FIX_ROUNDS = args && Number.isInteger(args.maxFixRounds) ? args.maxFixRounds : 2
const SPECS = (args && args.specs) || []

if (!SPECS.length) {
  log('No specs passed in args.specs — nothing to deliver.')
  return { units: [] }
}

const GATE = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    passed: { type: 'boolean' },
    outputTail: { type: 'string' },
  },
  required: ['name', 'passed'],
}

const IMPL = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    branch: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } },
    gates: { type: 'array', items: GATE },
    summary: { type: 'string', description: 'What was built, mapped to requirement IDs' },
    deviations: { type: 'array', items: { type: 'string' } },
    blockedReason: { type: 'string' },
  },
  required: ['status', 'branch', 'gates', 'summary'],
}

const REVIEW = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['approve', 'changes'] },
    score: { type: 'integer', minimum: 1, maximum: 10, description: 'Overall quality of the side, 1-10 (see the reviewer agent)' },
    gates: { type: 'array', items: GATE },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          issue: { type: 'string' },
          fix: { type: 'string' },
          requirement: { type: 'string', description: 'Requirement ID, if the finding traces to one' },
        },
        required: ['severity', 'file', 'issue', 'fix'],
      },
    },
    uncoveredRequirements: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['verdict', 'score', 'findings', 'summary'],
}

const sideBranch = (spec, side) => `feat/${spec.id}-${side}`

const implementPrompt = (spec, side) => `Implement the ${side} side of the approved spec in \`${spec.dir}\`.

- Spec ID: ${spec.id}. Base branch: \`${BASE}\`. Your worktree starts from it.
- RESUME: an earlier interrupted run may have left work on \`${sideBranch(spec, side)}\`. First run \`git rev-parse --verify --quiet ${sideBranch(spec, side)}\`. If it exists, \`git reset --hard ${sideBranch(spec, side)}\` and continue from it: read every commit since \`${BASE}\` (a "wip" commit holds unreviewed carry-over, verify it against the spec and fix or redo what is wrong), then finish the remaining tasks. Do not discard that work.
- When done, point \`${sideBranch(spec, side)}\` at your last commit with \`git branch -f ${sideBranch(spec, side)} HEAD\`. Do not push.
- Work only in the paths the root CLAUDE.md lists for the \`${side}\` side (section "Sides") and in \`${spec.dir}/state-${side}.md\`.
- You are the ${side} developer of an approved spec (level L), not a level M executor: build against the spec and tasks.md, not a brief.
- Follow your agent instructions (worktree bootstrap, commit format) and the operating mode in the root CLAUDE.md (for example Demo mode: no new tests, gates run once at the end).

Return the structured report. Set status "blocked" with blockedReason if you could not finish, and still point the branch at whatever you committed.`

const reviewPrompt = (spec, side, round) => `Review the ${side} side of spec ${spec.id} (\`${spec.dir}\`).

- Branch under review: \`${sideBranch(spec, side)}\`. Base: \`${BASE}\`. Review round ${round}.
- Check out the branch in detached mode in your worktree, bootstrap it (\`scripts/worktree-init ${side}\`), diff \`${BASE}...HEAD\` over the paths of the \`${side}\` side (root CLAUDE.md, section "Sides"), and re-run the gates yourself (\`scripts/gates ${side}\`).
- Requirements in scope: those in spec.md that tasks.md assigns to ${side}.

Return the structured verdict with a score from 1 to 10. "approve" only if there are no blocker and no major findings.`

const fixPrompt = (spec, side, review, round) => `Fix review findings on the ${side} side of spec ${spec.id} (\`${spec.dir}\`). Fix round ${round}.

1. Put your worktree on the reviewed code: \`git reset --hard ${sideBranch(spec, side)}\`.
2. Address every blocker and major finding below. Address minor findings where the fix is local and safe. If you disagree with a finding, do not silently skip it: write why in \`${spec.dir}/state-${side}.md\` and list it in deviations.
3. Unless the root CLAUDE.md operating mode says no new tests (Demo mode), add or adjust tests so each fixed bug has a test that would have caught it.
4. Re-run all your gates, commit, then \`git branch -f ${sideBranch(spec, side)} HEAD\`. Do not push.

Review findings (JSON):
${JSON.stringify({ findings: review.findings, uncoveredRequirements: review.uncoveredRequirements || [], gates: (review.gates || []).filter(g => !g.passed) }, null, 2)}`

const units = SPECS.flatMap(spec => (spec.touches || []).map(side => ({ spec, side })))
log(`Delivering ${SPECS.length} spec(s) as ${units.length} side(s), up to ${MAX_FIX_ROUNDS} fix round(s) each.`)

const results = await pipeline(
  units,
  u => agent(implementPrompt(u.spec, u.side), {
    label: `impl ${u.spec.id}/${u.side}`,
    phase: 'Implement',
    agentType: 'executor',
    isolation: 'worktree',
    schema: IMPL,
  }),
  async (impl, u) => {
    const history = []
    if (!impl) {
      return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: 'failed', impl: null, reviews: history }
    }
    if (impl.status === 'blocked') {
      log(`${u.spec.id}/${u.side} blocked: ${impl.blockedReason || 'no reason given'}`)
      return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: 'blocked', impl, reviews: history }
    }

    let current = impl
    for (let round = 1; round <= MAX_FIX_ROUNDS + 1; round++) {
      const review = await agent(reviewPrompt(u.spec, u.side, round), {
        label: `review ${u.spec.id}/${u.side} #${round}`,
        phase: 'Review',
        agentType: 'reviewer',
        isolation: 'worktree',
        schema: REVIEW,
      })
      if (!review) {
        return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: 'failed', impl: current, reviews: history }
      }
      history.push(review)
      const blocking = review.findings.filter(f => f.severity !== 'minor').length
      log(`${u.spec.id}/${u.side} review #${round}: ${review.verdict}, score ${review.score}/10 (${blocking} blocker/major, ${review.findings.length - blocking} minor)`)
      if (review.verdict === 'approve') {
        return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: 'approved', impl: current, reviews: history }
      }
      if (round > MAX_FIX_ROUNDS) break

      const fixed = await agent(fixPrompt(u.spec, u.side, review, round), {
        label: `fix ${u.spec.id}/${u.side} #${round}`,
        phase: 'Fix',
        agentType: 'executor',
        isolation: 'worktree',
        schema: IMPL,
      })
      if (!fixed || fixed.status === 'blocked') {
        return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: fixed ? 'blocked' : 'failed', impl: fixed || current, reviews: history }
      }
      current = fixed
    }
    log(`${u.spec.id}/${u.side} still has blocking findings after ${MAX_FIX_ROUNDS} fix round(s) — needs a human.`)
    return { id: u.spec.id, side: u.side, branch: sideBranch(u.spec, u.side), outcome: 'needs-human', impl: current, reviews: history }
  },
)

const done = results.filter(Boolean)
const dropped = units.length - done.length
if (dropped) log(`${dropped} side(s) produced no result (agent skipped or crashed).`)

return {
  base: BASE,
  units: done.map(r => ({
    id: r.id,
    side: r.side,
    branch: r.branch,
    outcome: r.outcome,
    implSummary: r.impl ? r.impl.summary : null,
    deviations: r.impl ? r.impl.deviations || [] : [],
    blockedReason: r.impl ? r.impl.blockedReason || null : null,
    reviewRounds: r.reviews.length,
    finalReview: r.reviews.length ? r.reviews[r.reviews.length - 1] : null,
  })),
}
