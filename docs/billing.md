# Affine billing map

The billing overlay is a transparent 456 × 300 Cairo object on the right side
of every monitor. The diamond is scaled from the 420px mockup so its width
sits a hair under the weather card, with a slight vertical tuck for a flatter isometric
read. Darker faces drop straight down from the chart plane so it reads as a
thin isometric tile rather than a sheared slab. It is the selected Affine Month Map from the preserved
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
- A provider glyph marks the current observation. A solid trail of stored
  daily observations sits on the past side of the yellow now-line. A dotted
  segment is the now-to-EOM forecast, and the hollow diamond is the EOM
  landing. GitHub, OpenRouter, Azure, Blacksmith, and AWS use their
  recognizable Octocat, geometric `OR`, official folded Azure `A`, C-block,
  and orange smile-arrow marks; providers without a compact vector mark
  retain the filled bead. OpenRouter is `#c8ff00`; Blacksmith's glyph is
  the charcoal C-block with a thin `#f0fb29` outline; Azure's glyph uses
  the brand folded-A blues; AWS's glyph is the brand smile `#ff9900`. Trails
  and forecast segments meet each glyph's painted outline, so they do not
  run under the mark or leave a circular gap around a non-round logo.
  Diamonds carry no text labels or leader lines.
- A dimmed trajectory means its last successful value is being retained after
  a failed refresh. A bead with no forecast line or diamond means there is not
  yet enough real history to calculate a forecast.

AWS is normalized against its live monthly COST budget. The component never
adds provider dollar values together. Current pressure is month-to-date spend
divided by that budget. The forecast uses current calendar pace:

```text
forecast spend = current spend × days in month ÷ current day
```

The AWS ceiling is `BudgetLimit` from the Budgets API. The Billing
console's default budget, which only excludes Credit and Refund record types,
still counts as account-wide. If more than one such budget exists, the
smallest USD limit is used. A CloudWatch `AWS/Billing` `EstimatedCharges`
alarm in `us-east-1` is the fallback when no monthly COST budget exists.
Azure's ceiling is the live credit balance at the start of the month. None of
those ceilings are configured in `.env`.

When no provider has usable billing data, the map is dimmed and a solid red
`NO BILLING DATA` popup is drawn over its center with a prompt to check the
billing log. Valid stale values still render, dimmed. The popup is reserved
for the state where there is nothing trustworthy to plot.

## Observation history

Every successful collect stores that day's observation for every live
provider. The solid past trail is that series growing over time: one sample
per provider per local calendar date, overwritten by later fetches on the
same day. The map plots stored days in the current month that are before
today. It does not invent missing days, interpolate across gaps, or write a
sample when a refresh failed and the previous value is only being retained as
stale.

The trail therefore starts at the earliest stored day, not at the month
origin. A provider holding one stored day draws one short segment into its
glyph, not a full-month diagonal down to the start-of-month corner.

This is independent of whether a provider exposes a daily API. AWS and
GitHub Actions therefore gain a trail only on days the fetcher actually
ran. Azure still seeds the same store from Cost Management daily rows when
those are available, and Blacksmith seeds it from `blacksmith usage` daily
totals, so those trails can be complete even if the overlay was not running on
those days. OpenRouter's plotted pressure is remaining-runway
future draw (the bead stays on the now-line at zero), so its stored trail sits
on the baseline; the same file still keeps dated total-usage samples for the
burn-rate fallback.

Do not drop this store in favor of “current bead plus forecast only.” The
intention is that history accumulates from collection and is what draws the
historical line.

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
throttled) are written into the shared observation store as cumulative
`Y_d / X` for each past day of the month, alongside today's collect. That
trail stays left of the now-line; the dotted forecast is the prediction.

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
the authenticated `blacksmith` CLI is using. Enable it with
`BILLING_BLACKSMITH_ENABLED`; do not set a cap. `blacksmith usage` returns
`billable_minutes` as 1-vCPU weighted minutes. The advertised x64 2vCPU
allowance is 3,000 minutes. The map divides billable by two so the current
point is 2vCPU minutes consumed divided by that allowance, then projects
calendar pace through the common EOM. Daily CLI totals seed the past trail
the same way Azure Cost Management rows do.

Org login follows `BILLING_BLACKSMITH_ORG` when set, otherwise the CLI's
current installation. Auth is `blacksmith auth login`.

## Live sources

- AWS uses boto3. Month-to-date spend is Cost Explorer
  [`UnblendedCost`](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html).
  The 100% line is an account-wide monthly COST
  [`BudgetLimit`](https://docs.aws.amazon.com/cost-management/latest/APIReference/API_budgets_DescribeBudgets.html)
  when one exists, otherwise a CloudWatch billing-alarm threshold. Enable it
  with `BILLING_AWS_ENABLED`; do not set a cap.
- Azure uses the authenticated Azure CLI. Starting and remaining credits
  come from the billing-profile [Consumption credits](https://learn.microsoft.com/en-us/rest/api/consumption/credits/get)
  `currentBalance` and `estimatedBalance`. Month-to-date spend is their
  difference, with [Cost Management](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01)
  `ActualCost` / `PreTaxCost` as fallback (converted to USD when billed in
  another currency; usage-detail `costInUSD` if Cost Management is throttled).
- OpenRouter uses a management key for the [credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits) and [analytics](https://openrouter.ai/docs/cookbook/administration/analytics-cost-control) endpoints.
- GitHub Actions uses the authenticated `gh` CLI to read the personal-account
  [billing usage report](https://docs.github.com/en/rest/billing/usage) and
  repository visibility. The token needs the `user` scope. Plan allowances and
  free public-repository behavior follow GitHub's
  [Actions billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
- Blacksmith uses the authenticated `blacksmith` CLI `usage` command for the
  current GitHub organization. Spend comes from that response; the free-minute
  ceiling is the advertised 3,000 x64 2vCPU minutes. They are not configured
  in `.env`.

Current spend, current balance, burn rate, and forecasts are always fetched or
derived. They are never configured in `.env`. The complete setup variables are
listed in [Configuration](configuration.md#affine-billing-map).

## AWS credentials

The overlay polls every 15 minutes unattended, so it cannot depend on an
`aws login` / SSO session. Terraform creates IAM user
`conky-billing-reader` with no console password and an inline policy that
allows only `ce:GetCostAndUsage`, `budgets:ViewBudget`, and
`cloudwatch:DescribeAlarms`. `scripts/apply_aws_billing_iam.sh` uses your
existing AWS identity once to create that user, then writes
`BILLING_AWS_ACCESS_KEY_ID` and `BILLING_AWS_SECRET_ACCESS_KEY` into `.env`.
Those keys take precedence; `BILLING_AWS_PROFILE` or the default boto3
chain are fallbacks. boto3 comes from `uv sync`. Local Terraform state
holds the same secret; it is gitignored. Rotate by replacing `aws_iam_access_key.billing_reader` and
re-running the script. Cost Explorer / Budgets SDK calls are not gated on
the Billing console's "Activate IAM Access" toggle.

AWS Cost Explorer queries are cached daily (`cache/billing-aws-cache.json`,
TTL `BILLING_AWS_CACHE_TTL_SECONDS` default `86400`) because AWS billing data
refreshes once per day and each Cost Explorer API call incurs a $0.01 fee.

## Placement and lifecycle

The launcher creates one billing window per monitor. With `BILLING_GAP_Y`
unset, the map sits just above the bottom-right weather panel. With
`BILLING_GAP_X` unset, its horizontal center follows the weather card; an
explicit value overrides that alignment. The fetch loop is independent of the GitHub contribution
skyline and does not read or write any GitHub cache or renderer state.

Cache and log ownership are documented in [Caches](caches.md). The renderer's
operation-dump replay is retained with the original mockup so the shipped Lua
geometry can be compared directly against the selected Pycairo design.
