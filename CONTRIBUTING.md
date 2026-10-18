# Contributing to Gateway7

Gateway7 is the Modular LLM Gateway built by Team 7 for the ITPD course.
The [Definition of Done](docs/definition-of-done.md) is the single source for completion criteria for stories, tasks and pull requests.
Follow [AGENTS.md](AGENTS.md) when using an AI agent, and use the [setup guide](docs/setup.md) to run the gateway and its checks.

## Commit messages

Write an imperative English subject of at most 72 characters, for example:

```text
Add the documentation build and Pages workflow
```

Use an optional body to explain a decision or a check that the subject cannot convey.
Include the AI tool's required `Co-authored-by:` trailer when it assists the commit, as [AGENTS.md](AGENTS.md#git) requires.
Conventional Commits prefixes are optional; the imperative subject and length limit remain the team's rule.

## From a task to a merged change

1. Open a task using the repository's [task issue form](https://github.com/iteam7/gateway7/issues/new?template=task.yml).
   Describe one unit of work and observable `AC-nn` acceptance criteria.
   When it works toward a story, name that story and the relevant story criteria in the form's `Story` field; leave that field empty for standalone documentation or workflow work.
2. Work on a branch named `<issue-number>-<short-lowercase-description>`, such as `54-publish-docs-workflow`.
   Create it from the task where GitHub supports this.
   Keep changes focused on that task and never commit directly to `main`.
3. Run the checks relevant to the change, then open one pull request for the task using the [pull request template](.github/pull_request_template.md).
   Include what changed and why, decisions and verification results, reviewer guidance, and one closing-keyword line such as `Closes #54`.
   A task that needs several pull requests must be split; a story is never this pull request's closing issue.
4. The accountable reviewer checks the task's criteria and the linked [Pull Request standard](docs/definition-of-done.md#pull-request), records any required corrections, and ticks the task's acceptance criteria before approving.
   An AI review does not replace the approval of another team member.
5. Merge through the pull request after all task criteria are ticked, the checks are green and the required independent approval is present.
   Keep a stacked pull request's dependency explicit; merging into another working branch does not complete its task.
   The task completes when its change reaches `main`; story closure follows the [Story standard](docs/definition-of-done.md#story).

Preserve pull requests, reviews and branches used as assignment evidence.
Do not rewrite shared history; the course's exception is removing accidentally committed sensitive data.
Dependabot and the course's automatic Done-task cleanup workflow are the exceptions to the task-issue requirement.

## Project views and scheduling

The public [Gateway7 project](https://github.com/orgs/iteam7/projects/1) and its [Sprints table view](https://github.com/orgs/iteam7/projects/1/views/3) are linked for the team's schedule.
The setup account in [PR #82](https://github.com/iteam7/gateway7/pull/82) records adding every open repository issue and enabling auto-add for new issues.
The earlier [task #79](https://github.com/iteam7/gateway7/issues/79) check observed `Assignees`, `Status`, `Linked pull requests` and `Sub-issues progress` in [View 1](https://github.com/orgs/iteam7/projects/1/views/1); it did not establish the required role fields, milestone organization or full issue coverage.
The live Sprints layout, issue coverage and auto-add configuration were not independently rechecked during this documentation update.

| View | What it shows and why | Current status |
| --- | --- | --- |
| [Sprints table (View 3)](https://github.com/orgs/iteam7/projects/1/views/3) | Required layout: every open repository issue, with `Responsible`, `Accountable`, `Assignees` and `Milestone` columns, grouped or sorted by `Milestone`, so work and verification responsibility are visible by sprint | Reported configured for [task #66](https://github.com/iteam7/gateway7/issues/66), grouped by `Milestone`; live configuration not independently rechecked in this update |
| [Public project table (View 1)](https://github.com/orgs/iteam7/projects/1/views/1) | The public table checked for task #79; its observed columns are listed above | Public access verified in that check; required layout remained unverified |
| [Repository milestones](https://github.com/iteam7/gateway7/milestones) | The issues in each sprint and their open/closed state; the milestone is the sprint backlog rather than a copied task list | The seven sprint milestones, `SPRINT-03` to `SPRINT-09`, exist with their weeks' hard deadlines as due dates |

When scheduling an issue, set its sprint milestone, two different members as `Responsible` and `Accountable`, and those same two members as its only assignees.
`Responsible` and `Accountable` are the organization's public single-select issue fields, with one option per member's GitHub username; set them in the issue's sidebar, not in the issue form.
The responsible member does the work; the accountable member verifies it.
An unscheduled open issue carries no milestone, role values or assignees.
Keep these values together when rescheduling or changing responsibility; do not invent values for work that has not been assigned.

## Checks and documentation

The [setup guide](docs/setup.md#checks-and-tests) contains the locked Python checks and HTTP demonstration.
The Markdown and Lychee workflows check repository Markdown and links on pull requests and pushes to `main`.
Maintain product and process documentation in `docs/`; weekly evidence stays in `reports/week-NN/`.
The documentation site serves only `docs/`.

### Build and preview the site

Use Python 3.12, uv and Node.js 24; the workflow pins their versions.
From the repository root:

```sh
uv venv --python 3.12.14 .venv-docs
uv pip sync --python .venv-docs/bin/python --require-hashes requirements-docs.txt
npm ci --prefix docs-build --ignore-scripts --no-audit --no-fund
.venv-docs/bin/mkdocs build --strict
.venv-docs/bin/python docs-build/check_site.py
.venv-docs/bin/mkdocs serve
```

The preview is at `http://127.0.0.1:8000/gateway7/`.
These commands use an isolated docs environment; `site/` is generated output and is ignored.
Keep the landing page in `docs/README.md` and navigation in `mkdocs.yml` current when adding a page.
The generated-site check verifies page coverage, local links and anchors, local browser assets, and the exclusion of weekly evidence.
Preview Mermaid changes in a browser as well; the architecture's Customer view must retain its upward response arrows.

Links from `docs/` to files outside it use full GitHub URLs.
Historical report citations keep their source hyperlinks in the repository and render as plain text on the site.
The site bundles its locked Mermaid asset locally.

The [documentation workflow](.github/workflows/docs.yml) builds and validates pull requests.
It publishes only successful `main` builds, on push or a manual run on `main`, through the `github-pages` environment.
Before the first deployment, a repository administrator opens **Settings → Pages → Build and deployment** and selects **GitHub Actions** as the source.
The deploy job alone receives Pages and identity-token write permissions.
The `github-pages` environment's deployment policies still apply.

Once the reviewed documentation changes reach `main`, that push can build and publish the site.
To retry, open **Actions → Documentation site → Run workflow** and select `main`; a manual run becomes available once the workflow exists on the default branch.
After the **Publish documentation** job succeeds, open its deployment URL and check the home page and navigation before replacing the root README's pending address with the verified site hyperlink.

### Update documentation dependencies

Edit the exact MkDocs version in `requirements-docs.in`, then regenerate its complete hash lock:

```sh
uv pip compile requirements-docs.in --python-version 3.12 --universal \
  --generate-hashes --output-file requirements-docs.txt
```

Add `--upgrade` when intentionally refreshing transitive dependencies.
For Mermaid, select an exact version in `docs-build/package.json`, then run:

```sh
npm install --prefix docs-build --package-lock-only --ignore-scripts
```

Commit the manifest and its lockfile together and rerun the site checks.
Dependabot checks the docs' pip and npm dependencies as well as the existing uv dependencies and GitHub Actions pins.
Every workflow action uses a released full commit SHA with its version comment; update both together.
