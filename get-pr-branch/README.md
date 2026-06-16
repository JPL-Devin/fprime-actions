# nasa/fprime-actions/get-pr-branch

This action is used for the [Automated Checks on Reference Repositories](https://github.com/nasa/fprime/blob/devel/CONTRIBUTING.md#automated-checks-on-reference-repositories) workflow. 

It checks a repo for whether or not a valid pr-xxxx branch exists, and if so, it sets the branch name as an output variable. If not, it returns a default branch name.

Will return a target branch in the following priority:

- If the event that triggered this action is a PR and has a matching `pr-<number>` branch on target_repository, then return the name of that branch. 
- If the name of the branch the PR is trying to merge into has a matching branch name on target_repo, then return that branch name. (this is useful for example for release/ branches, to have a tracking release branch on the her repo)
- Otherwise, return default_target_ref.

API calls are authenticated using the automatic `github.token` by default, which avoids the low unauthenticated GitHub API rate limit (60 requests/hour per runner IP) that can otherwise cause the lookup to silently fall back to the default branch. The optional `github-token` input only needs to be set to override this default (e.g. when cross-repository access requires a different token).
