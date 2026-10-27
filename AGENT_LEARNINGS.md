# Agent learnings

Confirmed agent mistakes in this repository, one lesson each; read the entries whose trigger matches the task.

## When you clean up after merging a PR
Never fold `git branch -D` (or `-d -f`) into a sync command: a forced branch delete needs the owner's separate yes; after a squash merge leave the local branch and say so.
Evidence: 2026-10-26, after merging #1 a combined `switch && pull && branch -D` was refused by the auto-mode classifier.
Enforced by: judgment; the auto-mode classifier refused it once

## When a workflow step prints untrusted text to the log
One line is not enough: the runner also runs legacy `##[command]` text found anywhere in a line, so print it between `::stop-commands::<random token>` and `::<token>::`.
Evidence: 2026-10-27, the failure-reason step claimed "no workflow command" after checking only `::`; both round-1 reviewers reproduced `##[add-mask]` from actions/runner `ActionCommand.TryParse` (`IndexOf`).
Enforced by: `tests/test_failure.py` for `merge_gate/failure.py`; judgment for new steps

## When you write which review-checklist triggers fire
Run the checklist's path and diff `rg` commands literally over the whole diff, recorded fixtures included, and report what they hit; never judge from the code alone.
Evidence: 2026-10-28, #5's round-1 self-check said "no trigger fires"; the reviewer ran the commands and `token`, `role` and `secrets.` hit `tests/fixtures/hindsight/merge-gate.json`.
Enforced by: judgment
