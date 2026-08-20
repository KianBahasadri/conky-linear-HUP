# Affine billing map

The billing overlay is a transparent 280 × 300 Cairo object on the right side
of every monitor. It is the selected Affine Month Map from the preserved
[design study](billing-mockups/README.md), shipped without a surrounding card,
header, legend, or footer.

## Reading the map

The diamond is an affine transform of an ordinary time-by-budget chart. Its
geometry is unusual, but the underlying axes are conventional:

- The long time edge runs from the first through the final day of the current
  local calendar month. Its endpoints are intentionally unlabeled.
- The yellow cross-line marks the current day divided by the number of days in
  that month.
- The red boundary is 100% of each provider's own ceiling. The faint band
  beyond it makes an over-cap forecast cross a real boundary instead of merely
  changing color. Neither boundary carries a text label.
- The dashed diagonal is calendar pace: 50% of the month against 50% of cap.
- A provider glyph marks the current observation. A solid trail through
  observed daily spend sits on the past side of the yellow now-line. A dotted
  segment is the now-to-EOM forecast, and the hollow diamond is the EOM
  landing. GitHub, OpenRouter, Azure, and Blacksmith use their recognizable
  Octocat, geometric `OR`, official folded Azure `A`, and yellow-plate C-block
  marks; providers without a compact vector mark retain the filled bead.
  OpenRouter is `#c8ff00`; Blacksmith's glyph is the `#f0fb29` plate with the
  charcoal C-block; Azure's glyph uses the brand folded-A blues; the other
  providers keep the mockup palette. Trails
  meet the marker edge without continuing underneath the service glyph.
  Diamonds carry no text labels or leader lines.
- A dimmed trajectory means its last successful value is being retained after
  a failed refresh. A bead with no forecast line or diamond means there is not
  yet enough real history to calculate a forecast.

AWS and Anthropic are normalized separately. The component never adds their
dollar values together. Their current pressure is month-to-date spend divided
by the configured cap. Their forecast uses current calendar pace:

```text
forecast spend = current spend × days in month ÷ current day
```

Those caps are personal surprise-bill thresholds, not values inferred from a
cross-provider total. Azure does not use a configured cap; its ceiling is the
live credit balance at the start of the month.

When no provider has usable billing data, the map is dimmed and a solid red
`NO BILLING DATA` popup is drawn over its center with a prompt to check the
billing log. Valid stale values still render, dimmed. The popup is reserved
for the state where there is nothing trustworthy to plot.

## OpenRouter

OpenRouter is prepaid, so its percentage has a deliberately different meaning
while sharing the same visual EOM edge:

1. The credits API supplies total credits and total usage; their difference is
   today's available balance.
2. The analytics API supplies actual usage over the trailing 30 days. Average
   daily burn is that real 30-day spend divided by 30.
3. Expected future draw is average daily burn multiplied by the number of days
   remaining through the common calendar EOM.
4. The plotted pressure is expected future draw divided by today's available
   balance. The bead therefore starts at zero future draw on the current-day
   line.

If the analytics endpoint is unavailable, the fetcher derives burn from its
own dated total-usage observations. It does not invent history: until two dates
exist, OpenRouter renders its current bead with no forecast line or diamond.
Top-ups do not distort this fallback because it uses cumulative total usage,
not changes in remaining balance.

## Azure

Azure is prepaid, but it is plotted as this month's consumption against the
credit pool the month started with, not as OpenRouter's remaining-balance
runway:

1. The authenticated Azure CLI reads the Microsoft Customer Agreement
   [credit balance](https://learn.microsoft.com/en-us/rest/api/consumption/credits/get) for the billing profile. `currentBalance` is the starting
   pool (posted credit). `estimatedBalance` is that pool after pending
   eligible charges.
2. Spent this month is starting credit minus remaining credit (`X − (X − Y)
   = Y`). That is the current observation.
3. The forecast uses current calendar pace of that spend through the common
   EOM, divided by the same starting pool.

The glyph therefore sits on the current-day line at `Y / X`, and the hollow
diamond is the EOM landing against that same `X`. Remaining credit is kept
as a diagnostic, not as the map's 100% ceiling.

Daily Cost Management rows (usage-detail `costInUSD` if that query is
throttled) become a solid trail of cumulative `Y_d / X` for each past day of
the month. That trail stays left of the now-line; the dotted forecast is the
prediction.

If the credit summary omits spend, month-to-date Cost Management (or usage
`costInUSD` when Cost Management is throttled) fills `Y`.

## GitHub Actions

GitHub Actions is an included-minutes allowance rather than a dollar cap. When
enabled, `GH` uses the plan reported for the account currently authenticated in
`gh`; GitHub Free supplies 2,000 minutes per month and GitHub Pro supplies
3,000. The current point is private-repository standard-runner minutes divided
by that allowance, and the landing projects the same live month pace through
the common EOM.

The detailed billing report does not identify whether a private-repository job
was free because it came from Dependabot or GitHub Pages. Those minutes are
therefore counted conservatively. Public-repository standard-runner minutes are
identified from live repository visibility and excluded, while larger runners
and storage are excluded from the minutes percentage because they have separate
billing rules. The JSON cache retains GitHub's reported net Actions charge as a
separate `currentPayableUsd` diagnostic.

## Blacksmith

Blacksmith is an included-minutes allowance for the GitHub organization that
the Firefox `app.blacksmith.sh` session is using. Enable it with
`BILLING_BLACKSMITH_ENABLED`; do not set a cap. The dashboard
[usage](https://app.blacksmith.sh) API returns `billable_minutes` as 1-vCPU
weighted minutes and `free_minutes` as the advertised x64 2vCPU allowance
(3,000 on the current free tier). The map divides billable by two so the
current point is 2vCPU minutes consumed divided by that live allowance, then
projects calendar pace through the common EOM. There is no daily history
endpoint, so Blacksmith renders the current bead and dotted forecast without a
past trail.

Org login follows `BILLING_BLACKSMITH_ORG` when set, otherwise the session's
`active_org_name`. Auth is the Firefox `blacksmith_session` cookie, or
`BILLING_BLACKSMITH_COOKIE` when that is set.

## Live sources

- AWS uses the authenticated [AWS CLI Cost Explorer](https://docs.aws.amazon.com/cli/latest/reference/ce/get-cost-and-usage.html) `UnblendedCost` total.
- Azure uses the authenticated Azure CLI. Starting and remaining credits
  come from the billing-profile [Consumption credits](https://learn.microsoft.com/en-us/rest/api/consumption/credits/get)
  `currentBalance` and `estimatedBalance`. Month-to-date spend is their
  difference, with [Cost Management](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01)
  `ActualCost` / `PreTaxCost` as fallback (converted to USD when billed in
  another currency; usage-detail `costInUSD` if Cost Management is throttled).
- Anthropic uses the organization [Cost Report API](https://platform.claude.com/docs/en/api/admin/cost_report). Amounts are returned in
  fractional cents and converted to USD. This requires an Admin API key and is
  not available to an individual Claude account.
- OpenRouter uses a management key for the [credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits) and [analytics](https://openrouter.ai/docs/cookbook/administration/analytics-cost-control) endpoints.
- GitHub Actions uses the authenticated `gh` CLI to read the personal-account
  [billing usage report](https://docs.github.com/en/rest/billing/usage) and
  repository visibility. The token needs the `user` scope. Plan allowances and
  free public-repository behavior follow GitHub's
  [Actions billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
- Blacksmith uses the Firefox `app.blacksmith.sh` session against the dashboard
  usage API for the active GitHub organization. Spend and the free-minute
  ceiling come from that response; they are not configured in `.env`.

Current spend, current balance, burn rate, and forecasts are always fetched or
derived. They are never configured in `.env`. The complete setup variables are
listed in [Configuration](configuration.md#affine-billing-map).

## Placement and lifecycle

The launcher creates one billing window per monitor. With `BILLING_GAP_Y`
unset, it centers the 300px map in the vertical lane between the top-right
resource HUD and bottom-right weather panel. With `BILLING_GAP_X` unset, its
horizontal center follows the resource monitor; an explicit value overrides
that alignment. The fetch loop is independent of the GitHub contribution rail and does
not read or write any GitHub cache or renderer state.

Cache and log ownership are documented in [Caches](caches.md). The renderer's
operation-dump replay is retained with the original mockup so the shipped Lua
geometry can be compared directly against the selected Pycairo design.
