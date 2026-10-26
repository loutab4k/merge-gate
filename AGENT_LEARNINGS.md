# Agent learnings

Confirmed agent mistakes in this repository, one lesson each; read the entries whose trigger matches the task.

## When you clean up after merging a PR
Never fold `git branch -D` (or `-d -f`) into a sync command: a forced branch delete needs the owner's separate yes; after a squash merge leave the local branch and say so.
Evidence: 2026-10-26, after merging #1 a combined `switch && pull && branch -D` was refused by the auto-mode classifier.
Enforced by: judgment; the auto-mode classifier refused it once
