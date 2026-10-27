# merge-gate hindsight eval

As of 2027-03-20T00:00:00+00:00, window 3 days, repos: owner/proj. 15 verdicts, 4 gate-marked comments skipped.

Bad outcome: reverted, main-red, fixed-soon or model-bad. Settled: bad, clean or model-clean. `pending`: merged less than the window ago with nothing bad yet. `ambiguous`: a related later PR that no deterministic rule settles and no model grade decided.

## Outcomes

| label | would-merge | manual |
|---|---|---|
| reverted | 3 | 0 |
| main-red | 0 | 1 |
| fixed-soon | 2 | 0 |
| pending | 1 | 0 |
| ambiguous | 3 | 0 |
| clean | 1 | 2 |
| closed-unmerged | 1 | 0 |
| open | 1 | 0 |

## Would-merge followed by a bad outcome

5 of 6 (83%) settled would-merge verdicts.

## Manual verdicts

A manual verdict was needed when the PR still had a bad outcome. A `review` manual verdict (only the review asked for a human) on a PR that stayed clean is review noise; a `rule` one is the gate's policy; a `no-review` one means the review step failed.

- `review`: 1 verdicts; bad outcome in 0 of 1 (0%) settled; 0 unsettled or unmerged.
- `rule`: 1 verdicts; bad outcome in 1 of 1 (100%) settled; 0 unsettled or unmerged.
- `no-review`: 1 verdicts; bad outcome in 0 of 1 (0%) settled; 0 unsettled or unmerged.

## Reviewer verdict against outcome

| review | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| None | 2 | 0 | 0 | 2 | 1 | 1 | 0 |
| manual | 1 | 0 | 0 | 1 | 0 | 1 | 0 |
| merge | 12 | 12 | 5 | 0 | 0 | 0 | 6 |

## By class

| class | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| code | 15 | 12 | 5 | 3 | 1 | 2 | 6 |

## By confidence

| confidence | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |
|---|---|---|---|---|---|---|---|
| 06 | 1 | 0 | 0 | 1 | 0 | 1 | 0 |
| 09 | 12 | 12 | 5 | 0 | 0 | 0 | 6 |
| none | 2 | 0 | 0 | 2 | 1 | 1 | 0 |

0 verdicts judged a head that is not the PR's final head.

## Skipped comments

- no record block: 1
- not a pull request: 1
- not written by the gate: 1
- record names another PR: 1
