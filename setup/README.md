# nasa/fprime-actions/setup

The `setup` action is used to quickly install dependencies for F Prime projects. It assumes that Python and pip are already installed on the system. The action will install the F´ requirements.txt.

Inputs: `location` (F´ checkout, default `$GITHUB_WORKSPACE`), `ccache` (default `true`), `ccache-key-suffix`, and `cache-mode` (`read-write` by default; `read` restores the pip and ccache caches but never saves them). Use `cache-mode: read` for any run that builds code it does not trust, such as a `workflow_dispatch` run that overlays an F´ pull-request revision: GitHub lets such runs write the default-branch cache that every later run restores.

```yaml
- uses: nasa/fprime-actions/setup@devel
  with:
    location: lib/fprime
    cache-mode: ${{ github.event_name == 'workflow_dispatch' && 'read' || 'read-write' }}
```
