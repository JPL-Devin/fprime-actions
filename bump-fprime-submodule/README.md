# Bump F´ submodule

This composite action resolves `nasa/fprime@devel` (or another configured
repository and ref), updates the caller's F´ submodule, initializes nested
submodules, and commits the change on a fixed branch.

If the pinned revision already matches the resolved revision, the action is a
no-op: it creates no branch and no commit. This makes it safe to run on every
push to the caller's default development branch.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `fprime-path` | `lib/fprime` | Path to the F´ submodule |
| `fprime-repository` | `nasa/fprime` | F´ repository |
| `fprime-ref` | `devel` | Branch or ref to resolve |
| `branch` | `auto/bump-fprime` | Fixed branch for the bump commit |

## Outputs

`bumped`, `old-sha`, `new-sha`, and `commit-count` describe the update.

## Example

```yaml
- uses: nasa/fprime-actions/bump-fprime-submodule@devel
  id: bump
```
