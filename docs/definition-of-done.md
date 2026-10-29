# Definition of done

This is Gateway7's standard for completing work.
Update it when the workflow changes.

## Story

- Every acceptance criterion passes on `main`.
- Every task issue that works on the story has closed with its pull request merged, so each also met the [Task](#task) and [Pull Request](#pull-request) lists below.
- The story issue links the evidence for each criterion.
- The accountable member has checked that each criterion is runnable and that every link on the issue resolves.

A story closes only on the Customer's acceptance.
Merged tasks or a successful demonstration alone do not record that acceptance.

## Task

- Every acceptance criterion the task carries is satisfied.
- The task closes as completed when the pull request that closes it merges into `main`.

## Pull Request

- The pull request closes exactly one task issue and links it with a closing keyword.
- The accountable reviewer ticks every task acceptance criterion before approving.
- Approval comes from a team member other than the author.
- The repository checks are green: Workflow check (`actionlint` over `.github/workflows/`), Link check, Markdown check, the documentation build, and Python checks with their formatting, linting, type checking, automated tests and build steps.
- A user-visible change updates the `[Unreleased]` section of `CHANGELOG.md`.
- The acceptance criteria the pull request claims pass on its branch and on `main` after it merges.
- No secret, recording or private-only material is committed.
- Implementation notes in the pull request description record the decisions made and how the change was checked.
