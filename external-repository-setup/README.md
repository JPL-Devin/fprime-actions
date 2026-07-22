# nasa/fprime-actions/external-repository-setup

The `external-repository-setup` action is used to set up a repository external to nasa/fprime that needs to build to guarantee nasa/fprime works.

By default the current repository (the one running the workflow) is overlaid onto the external project's F´ checkout at `fprime_location`. When the workflow belongs to another project used by the external repository (e.g. a library like `fprime_cfs`), set `overlay_location` to the path of that project within the external checkout instead.

```yaml
- uses: nasa/fprime-actions/external-repository-setup@devel
  with:
    target_repository: fprime-community/fprime_cfs_reference
    fprime_location: ./libs/fprime
    overlay_location: ./libs/fprime_cfs
```
