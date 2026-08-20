# Affine billing map

The billing overlay is a transparent 280 × 300 Cairo object on the right side
of every monitor. It is the selected Affine Month Map from the preserved
[design study](billing-mockups/README.md), shipped without a surrounding card,
header, legend, or footer.

## Reading the map

The diamond is an affine transform of an ordinary time-by-budget chart. Its
geometry is unusual, but the underlying axes are conventional:

- `DAY 1` to `EOM` is the current local calendar month.
- `NOW` is the current day divided by the number of days in that month.
- `CAP` is 100% of each provider's own ceiling. The faint band beyond it makes
  an over-cap forecast cross a real boundary instead of merely changing color.
- The dashed diagonal is calendar pace: 50% of the month against 50% of cap.
- A filled bead is the current observation, the colored segment is the
  now-to-EOM forecast, and the hollow diamond is the EOM landing.
- `~` after a provider label means its last successful value is being retained
  after a failed refresh. `--` means there is not yet enough real history to
  calculate a forecast.

AWS, Azure, and Anthropic are normalized separately. The component never adds
their dollar values together. Their current pressure is month-to-date spend
divided by the configured cap. Their forecast uses current calendar pace:

```text
forecast spend = current spend × days in month ÷ current day
```

The caps are personal surprise-bill thresholds, not values inferred from a
cross-provider total.

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
   balance. The bead therefore starts at zero future draw on `NOW`.

If the analytics endpoint is unavailable, the fetcher derives burn from its
own dated total-usage observations. It does not invent history: until two dates
exist, OpenRouter renders its current bead with `OR --` and no forecast line.
Top-ups do not distort this fallback because it uses cumulative total usage,
not changes in remaining balance.

## Live sources

- AWS uses the authenticated [AWS CLI Cost Explorer](https://docs.aws.amazon.com/cli/latest/reference/ce/get-cost-and-usage.html) `UnblendedCost` total.
- Azure uses the authenticated Azure CLI to query [Cost Management](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01)
  `ActualCost` / `PreTaxCost` for month to date.
- Anthropic uses the organization [Cost Report API](https://platform.claude.com/docs/en/api/admin/cost_report). Amounts are returned in
  fractional cents and converted to USD. This requires an Admin API key and is
  not available to an individual Claude account.
- OpenRouter uses a management key for the [credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits) and [analytics](https://openrouter.ai/docs/cookbook/administration/analytics-cost-control) endpoints.

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
