# Open or update F´ bump PR

Pushes the fixed `auto/bump-fprime` branch and maintains one open pull request
for the repository. Repeated runs update that PR instead of opening a new PR.
The action uses only the caller repository's `GITHUB_TOKEN`.

The PR body includes the build result, revision compare link, and commit range.
Failed builds add the `bump-broken` label and document the `pr-<number>` manual
escape hatch for fprime-side breakage.

## Required permissions

```yaml
permissions:
  contents: write
  pull-requests: write
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `github-token` | `${{ github.token }}` | Repository-local token |
| `branch` | `auto/bump-fprime` | Fixed branch to push |
| `base` | `devel` | PR base branch |
| `fprime-repository` | `nasa/fprime` | F´ repository used for revision links |
| `build-result` | — | `success` or `failure` |
| `old-sha` | — | Previous F´ revision |
| `new-sha` | — | New F´ revision |
| `commit-count` | — | Commits between revisions |
