# merge-gate

A reusable GitHub workflow that decides whether a pull request could merge without a human, and posts that verdict on the PR. Version 1 runs in **shadow mode only**: it comments and never merges, so its verdicts can be compared with the owner's own decisions before anything is automated.

## What it checks

After the project's CI finishes on a PR's head commit (CI triggered by `pull_request` or by a branch `push`), the gate runs three jobs:

1. **assess** (deterministic, no PR code runs). The PR must come from this repository (fork PRs get no run and no comment), be open and not a draft, and come from the owner on an `ai/` branch or from Dependabot or Renovate. CI must be green. The diff must stay under the size cap (800 changed lines, 300 files). It must not touch a critical path, delete or rename a test file, or add a test-skip marker such as `t.Skip(`, `self.skipTest(`, `//go:build ignore` or `it.only(`. Any failure routes the PR to a human, and no model runs.
2. **review** (only when assess found nothing). Claude reads the diff, the PR head and the default branch with Read, Grep and Glob, and cannot read outside them. It treats the PR description as unverified claims, checks each acceptance criterion against the diff, and returns a JSON verdict. The job's GitHub token is read-only.
3. **report**. A pure function combines both results. The verdict is "would merge" only when the review says merge with confidence 8 or more, every criterion is met, nothing is `blocker` or `major`, and a PR other than a dependency bump has criteria at all. A missing or malformed review means "needs a human". The verdict goes into one comment per PR, edited on each run, with a JSON record at the end. Model-written text appears only as inline code, so it cannot mention anyone or load a link.

Critical paths always include `.github/**`, `.claude/**`, `.mcp.json`, and `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` and `.claude/` at any depth; they match ignoring case. A project adds its own.

A PR opened after its push CI already finished gets a verdict on its next push.

## Threat model

Everything a PR supplies is untrusted: file contents, paths, the diff, the title and the description. The gate triggers on `workflow_run`, which has the base repository's secrets, so it never executes PR code: assess and report only call the GitHub API, and review only reads the PR head as files. The Claude token sits in the review job, where the model reads untrusted text; that model has no shell, no write tools and no web tools, cannot read outside the checkouts or into `.git`, and the job's GitHub token can only read. The remaining risk is a PR that talks the reviewer into a wrong verdict (published attacks on LLM reviewers succeed often). The deterministic checks in assess run first and cannot be argued with, and in shadow mode a wrong verdict is only a wrong comment.

## Set up a project

1. Copy [`examples/merge-gate.yml`](examples/merge-gate.yml) to `.github/workflows/merge-gate.yml` and set `workflows:` to the `name:` of the project's CI workflow. On a self-hosted runner, pass its label as `runner`; the runner needs `python3` and `curl` on Linux x86-64.
2. Add `.github/merge-gate.json` on the default branch:

   ```json
   {
     "version": 1,
     "mode": "shadow",
     "owner": "your-login",
     "critical_paths": ["db/migrations/**", "internal/billing/**"]
   }
   ```

   Optional keys, with their defaults in [`merge_gate/config.py`](merge_gate/config.py): `agent_branch_prefix`, `bots`, `test_paths`, `docs_paths`, `dependency_files`, `max_changed_lines`. Unknown keys are an error.
3. Add the repository secret `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`). Without it, or once it expires, every review fails and every verdict is "needs a human"; replace it with a new one then.

The workflow and config run from the default branch, so a PR cannot change the rules it is judged by.

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

This repository runs the gate on its own PRs through `.github/workflows/merge-gate.yml`.
