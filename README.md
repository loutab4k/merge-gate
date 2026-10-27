# merge-gate

A reusable GitHub workflow that decides whether a pull request could merge without a human, and posts that verdict on the PR. Version 1 runs in **shadow mode only**: it comments and never merges, so its verdicts can be compared with the owner's own decisions before anything is automated.

## What it checks

After the project's CI finishes on a PR's head commit (CI triggered by `pull_request` or by a branch `push`), the gate runs three jobs:

1. **assess** (deterministic, no PR code runs). The PR must come from this repository (fork PRs get no run and no comment), be open and not a draft, and come from the owner on an agent branch (`ai/` by default) or from Dependabot or Renovate. CI must be green. The diff must stay under the size cap (800 changed lines, 300 files). It must not touch a critical path, delete or rename a test file, or add a test-skip marker such as `t.Skip(`, `self.skipTest(`, `//go:build ignore` or `it.only(`. Any failure routes the PR to a human. A critical path alone still gets the review, so shadow mode measures the reviewer on the riskiest PRs too; any other failure, agent config included, means no model runs.
2. **review** (when assess found nothing, or only critical paths). Claude reads the diff, the PR head and the default branch with Read, Grep and Glob, and cannot read outside them. It treats the PR description as unverified claims, checks each acceptance criterion against the diff, and returns a JSON verdict. The job's GitHub token is read-only. When the review step fails, the job logs why: only the final result's subtype, `is_error` and error text (such as a usage limit or an API error), cut to 300 characters, never the prompt or the diff.
3. **report**. A pure function combines both results. A critical path is always "needs a human", whatever the review says. Otherwise the verdict is "would merge" only when the review says merge with confidence 8 or more, every criterion is met, nothing is `blocker` or `major`, and a PR other than a dependency bump has criteria at all. A missing or malformed review means "needs a human"; when the review step failed, the `no-review` reason carries that error line. The verdict goes into one comment per PR, edited on each run, with a JSON record at the end. Model-written text appears only as inline code, so it cannot mention anyone or load a link.

Critical paths always include `.github/**`, and a project adds its own. Agent config is checked apart from them: `.mcp.json`, plus `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` and `.claude/` at any depth, including a symlink named `.claude`. A PR that edits agent config always needs a human and is never reviewed, because the reviewer would load skills, commands and agents from the PR head. Both lists match ignoring case.

A PR opened after its push CI already finished gets a verdict on its next push.

## Threat model

Everything a PR supplies is untrusted: file contents, paths, the diff, the title and the description. The gate triggers on `workflow_run`, which has the base repository's secrets, so it never executes PR code: assess and report only call the GitHub API, and review only reads the PR head as files. Each job uses a fresh `HOME` and runs Python with `-s -E`, so files left in a shared runner's home cannot inject code; a runner that also runs CI can still leave a process behind, hence the dedicated runner in "Set up a project". The Claude token sits in the review job, where the model reads untrusted text; that model loads no project settings, skills, commands, agents or CLAUDE.md from either checkout (`--setting-sources user`), has no shell, no write tools and no web tools, cannot read outside the checkouts or into `.git`, and the job's GitHub token can only read. A failed review's error text comes from the model or the API and may echo the PR, so it is treated like model text: one printable line, logged with workflow commands stopped, passed only through `env` and job outputs, never into a shell line, and shown in the comment as inline code. The remaining risk is a PR that talks the reviewer into a wrong verdict (published attacks on LLM reviewers succeed often). The deterministic checks in assess run first and cannot be argued with, and in shadow mode a wrong verdict is only a wrong comment.

## Set up a project

1. Copy [`examples/merge-gate.yml`](examples/merge-gate.yml) to `.github/workflows/merge-gate.yml` and set `workflows:` to the `name:` of the project's CI workflow. On a self-hosted runner, pass its label as `runner`: use a runner that never runs PR code (not the one CI uses), because a runner that keeps state between jobs would hand the Claude token to whatever a PR left behind. The runner needs `python3` and `curl` on Linux x86-64.
2. Add `.github/merge-gate.json` on the default branch:

   ```json
   {
     "version": 1,
     "mode": "shadow",
     "owner": "your-login",
     "critical_paths": ["db/migrations/**", "internal/billing/**"]
   }
   ```

   Optional keys, with their defaults in [`merge_gate/config.py`](merge_gate/config.py): `agent_branch_prefixes` (a list), `bots`, `test_paths`, `docs_paths`, `dependency_files`, `max_changed_lines`. Unknown keys are an error.
3. Add the repository secret `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`). Without it, or once it expires, every review fails and every verdict is "needs a human"; replace it with a new one then.

The workflow and config run from the default branch, so a PR cannot change the rules it is judged by.

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/mutation-check.py
```

The mutation check breaks each safety check in turn and fails unless a test catches it; extend it with every new check.

This repository runs the gate on its own PRs through `.github/workflows/merge-gate.yml`.

## Hindsight eval

`python3 -m hindsight` grades every shadow verdict by what happened to its PR afterwards, so the verdicts become an eval set. Run it on a machine where `gh` can read the repositories that call the gate (listed in `REPOS` in [`hindsight/__main__.py`](hindsight/__main__.py); `--repo` replaces the list). It only reads GitHub and writes `hindsight-out/dataset.jsonl` (one row per verdict, with its label and evidence links) and `hindsight-out/summary.md`. The output holds data of private repositories, so it stays out of Git.

Each merged PR gets the first label that applies, from what merged into its base within three days (`--window-days`):

- `reverted`: a later PR is GitHub's revert of it, names its merge commit after `This reverts commit` in the merge message or description, or has a branch commit of its own that reverts one of the PR's commits.
- `main-red`: a push run on its merge commit failed.
- `fixed-soon`: a later PR whose title says fix, bug, regression, broken or typo changed lines the PR wrote (GitHub blame at the later PR's parent).
- `pending`: the window is still open.
- `ambiguous`: a later PR names it, shares a file with it or changed its lines without a sign of a fix. With the model step these become `model-bad` or `model-clean`; `--no-model` leaves them.
- `clean`: none of the above.

Unmerged PRs are `open` or `closed-unmerged`. Only the comment the gate itself wrote counts, and its record must name the PR it sits on.

The model step sends each ambiguous case to `claude -p` without tools, settings or MCP servers; its answer must end in a fixed grade section, and anything else leaves the case `ambiguous`. Prompts and answers stay in `hindsight-out/grades/`, so a rerun asks the model nothing new. Model grades are unvalidated: check a sample by hand before trusting them.
