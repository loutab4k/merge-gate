# merge-gate hindsight eval

As of 2026-10-30T00:00:00+00:00, window 3 days, repos: loutab4k/merge-gate. 3 verdicts, 0 gate-marked comments skipped.

Bad outcome: reverted, main-red, fixed-soon or model-bad. Settled: bad, clean or model-clean. `pending`: merged less than the window ago with nothing bad yet. `ambiguous`: a related later PR that no deterministic rule settles and no model grade decided.

## Outcomes

| label | would-merge | manual |
|---|---|---|
| pending | 0 | 1 |
| ambiguous | 1 | 1 |

## Would-merge followed by a bad outcome

0 of 0 settled would-merge verdicts.

## Manual verdicts

A manual verdict was needed when the PR still had a bad outcome. A `review` manual verdict (only the review asked for a human) on a PR that stayed clean is review noise; a `rule` one is the gate's policy; a `no-review` one means the review step failed.

- `review`: 0 verdicts; bad outcome in 0 of 0 settled; 0 unsettled or unmerged.
- `rule`: 2 verdicts; bad outcome in 0 of 0 settled; 2 unsettled or unmerged.
- `no-review`: 0 verdicts; bad outcome in 0 of 0 settled; 0 unsettled or unmerged.

## Reviewer verdict against outcome

| review | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| None | 2 | 1 | 0 | 1 | 0 | 0 | 2 |
| manual | 1 | 0 | 0 | 1 | 0 | 0 | 1 |

## By class

| class | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| code | 3 | 1 | 0 | 2 | 0 | 0 | 3 |

## By confidence

| confidence | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| 06 | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| 08 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| none | 1 | 0 | 0 | 1 | 0 | 0 | 1 |

0 verdicts judged a head that is not the PR's final head.
