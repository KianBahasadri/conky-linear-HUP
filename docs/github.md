# GitHub overlay

- The GitHub tracker is a transparent left-side rail with only contribution squares.
- `GITHUB_USERNAME` controls the rendered account. `GH_USERNAME` is also accepted. If both are missing, the fetcher tries `git config github.user` and then the GitHub remote owner.
- `GITHUB_TOKEN` is optional and only used for authenticated requests to the public contributions endpoint.
- Set `GITHUB_OVERLAY_ENABLED=0` to disable the GitHub overlay and its refresh loop.
- `GITHUB_REFRESH_SECONDS`, `GITHUB_TIMEOUT_SECONDS`, `GITHUB_GAP_X`, and `GITHUB_GAP_Y` can tune refresh cadence, request timeout, and placement.

## Contribution calendar troubleshooting

- A gray rightmost square does not necessarily mean today's commits are missing. GitHub can already be showing the next UTC date while local time is still on the previous day; hover the squares to confirm their dates.
- GitHub may take up to 24 hours to refresh the contribution graph. If the expected square is still gray afterward, confirm that the commits are pushed to the repository's default branch and use an email address linked to the GitHub account.
