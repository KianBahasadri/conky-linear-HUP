# Billing forecast panel

Every provider shares one budget map in the right rail: an affine time-and-limit
plane whose near left edge is the start of the month and whose far edge is month
end. Shared appearance and layout are owned by the [Desktop design system](design-system.md).

## Reading the map

- The shared coordinate is percentage of each provider's own limit, never a sum
  of unrelated dollars, minutes, and balances. Prepaid OpenRouter retains the
  distinct runway meaning described below.
- The scale starts at zero and reaches 105%, leaving a translucent red band
  above the 100% limit line. Overruns expand the scale up to a maximum of 200%
  (capping the red overage band at 100%). When a forecast exceeds 200%, the scale
  does not expand further; the trajectory line terminates at the top boundary at
  the date it crosses 200%, placing its endpoint square along that side instead
  of reaching the month-end corner.
- A solid cyan trail with sample dots is real stored daily observations, ending
  at the current marker on the dashed now-line. Missing history days break the
  trail instead of being interpolated, and a single stored day stays a point.
- The current marker is the provider's own vector mark. A dashed violet
  connector runs from it toward the month-end edge, turning red only where it
  passes 100%.
- The forecast endpoint's shape is its severity: a circle within limit, a
  4px-radius square near the limit, and a sharp square for a projected overrun.
- Gridlines every 25 points, a faint dotted even-consumption pace line, and the
  dashed now-line are the map's only reference marks. It carries no text.
- With no providers at all, an explicit `Unavailable` callout replaces the map.

The earlier affine diamond and Cairo design sources are preserved in the
[billing design archive](billing-mockups/README.md). The design guide's own
budget map registers this repository's provider marks; `conky/provider-marks.lua`
holds the same vectors.

AWS is normalized against its live monthly COST budget. The component never
adds provider dollar values together. Current pressure is month-to-date spend
divided by that budget. The forecast uses a weighted daily pace so more recent
days pull harder, with simple calendar pace as fallback when history is short:

```text
forecast spend = current spend + weighted_daily_rate × days remaining
weighted_daily_rate = weighted average of per-day deltas (decay ≈ 6-day half-life)
fallback when not enough history: current spend × days in month ÷ current day
```

Tune with `BILLING_FORECAST_HALF_LIFE_DAYS` (default `2`) or `BILLING_FORECAST_DECAY`
(`0 < decay < 1`, half-life wins when set).

The AWS ceiling is `BudgetLimit` from the Budgets API. The Billing
console's default budget, which only excludes Credit and Refund record types,
still counts as account-wide. If more than one such budget exists, the
smallest USD limit is used. A CloudWatch `AWS/Billing` `EstimatedCharges`
alarm in `us-east-1` is the fallback when no monthly COST budget exists.
Azure's ceiling is the live credit balance at the start of the month. None of
those ceilings are configured in `.env`.

## Observation history

Every successful collect stores that day's observation for every live
provider. The solid observed trail is that series growing over time: one sample
per provider per local calendar date, overwritten by later fetches on the
same day. The charts plot stored days in the current month that are before
today. It does not invent missing days, interpolate across gaps, or write a
sample when a refresh failed and the previous value is only being retained as
stale.

The trail therefore starts at the earliest stored day, not at the month
origin. A provider holding one stored day draws one short segment into its
current observation, not a full-month line to the origin.

This is independent of whether a provider exposes a daily API. AWS and
GitHub Actions therefore gain a trail only on days the fetcher actually
ran. Azure still seeds the same store from Cost Management daily rows when
those are available, and Blacksmith seeds it from `blacksmith usage` daily
totals, so those trails can be complete even if the overlay was not running on
those days. OpenRouter's plotted pressure is remaining-runway
future draw (the current point stays on the now-line at zero), so its stored trail sits
on the baseline; the same file still keeps dated total-usage samples for the
burn-rate fallback.

Do not drop this store in favor of “current point plus forecast only.” The
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
   balance. The current point therefore starts at zero future draw on the current-day
   line.

If the analytics endpoint is unavailable, the fetcher derives burn from its
own dated total-usage observations. It does not invent history: until two dates
exist, OpenRouter renders its current point with no forecast line or endpoint marker.
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

The current point therefore sits on the current-day line at `Y / X`, and the hollow
square is the EOM landing against that same `X`. Remaining credit is kept
as a diagnostic, not as the plot's 100% ceiling.

Daily Cost Management rows (usage-detail `costInUSD` if that query is
throttled) are written into the shared observation store as cumulative
`Y_d / X` for each past day of the month, alongside today's collect. That
trail stays left of the now-line; the dashed forecast is the prediction.
After a daily Cost Management throttle, the fetcher uses Usage Details for six
hours before retrying Cost Management; the cooldown is persisted per Azure
subscription, so frequent polls do not keep hammering the throttled endpoint.

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
allowance is 3,000 minutes. The renderer divides billable by two so the current
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
listed in [Configuration](configuration.md#billing-forecast-panel).

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
holds the same secret; it is gitignored but is still sensitive local data.
`apply_aws_billing_iam.sh` uses a private process umask so new state and backup
files are `0600` from their first write, repairs existing state permissions
including on failed runs, and atomically replaces `.env` so an interruption
cannot truncate the rest of the configuration. Rotate by replacing
`aws_iam_access_key.billing_reader` and re-running the script. Cost Explorer / Budgets SDK calls are not gated on
the Billing console's "Activate IAM Access" toggle.

AWS Cost Explorer queries are cached daily (`cache/billing-aws-cache.json`,
TTL `BILLING_AWS_CACHE_TTL_SECONDS` default `86400`) because AWS billing data
refreshes once per day and each Cost Explorer API call incurs a $0.01 fee.

## Placement and lifecycle

The launcher creates one billing window per monitor in the right rail below
system resources. Explicit `BILLING_GAP_X`/`BILLING_GAP_Y` overrides retain their
right-edge/top-edge meaning. The fetch loop is independent of the GitHub
contribution calendar and does not read or write its cache or renderer state.
Cache and log ownership are documented in [Caches](caches.md).
