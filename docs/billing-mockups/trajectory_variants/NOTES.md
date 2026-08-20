# Trajectory / horizon billing studies

All four studies are 424 px wide and use the same illustrative 19 August snapshot:

- AWS: $8.41 of $25 now (34%), $13.20 EOM (53%).
- Azure: $4.27 of $20 now (21%), $7.10 EOM (36%).
- Anthropic: $6.04 of $20 now (30%), $10.10 EOM (50.5%).
- OpenRouter: $12.44 remaining at $0.43/day = 28.9 days of runway; 12 days remain in August.

There is no aggregate dollar total. Metered services share only dimensionless cap pressure; prepaid stays on a separately labelled day scale. Filled dots are current observations, open diamonds/tips are EOM forecasts, yellow is calendar pace or the 12-day reserve gate, and red is always the 100% cap horizon.

## 1. Landing Field

The direct time x cap graph. X is day 1–31; Y is spend/budget. Each line is only the honest current-to-forecast segment, with no invented historical samples. The diagonal is calendar pace and the red horizontal is the cap. OpenRouter uses a separate 0–40 day tower.

Recommendation: safest production choice and easiest to learn. It is the clearest reference against which to judge the more expressive versions.

## 2. Forecast Rain

The same coordinate system turned on its side: time falls from NOW to EOM, while cap pressure moves left-to-right. A forecast that breaches lands to the right of the red wall. The yellow diagonal is the on-pace landing. OpenRouter is a separate oblique 0–40 day number line with literal 12-day and 29-day points.

Recommendation: strongest fresh direction. It does not resemble the existing horizontal quota tubes, and the calm safe state is unusually sparse. Prototype this one alongside Landing Field.

## 3. Affine Cap Map

Time and cap pressure are transformed into a diamond using a reversible affine mapping. NOW, EOM, the cap horizon, and on-pace diagonal remain straight reference lines; provider points contain exactly the same values as Landing Field. The prepaid ray remains separate and explicitly uses days.

Recommendation: attractive exploration, but not the default. It asks the viewer to learn two diagonal axes and is less glanceable even though the geometry is honest.

## 4. Isometric Runway

Provider identity gets a lateral lane, time recedes into depth, and cap pressure is height. The translucent red parallelogram is the 100% cap plane. Each current dot flies to an EOM tip; the faint continuation from the tip to the plane is literal forecast headroom. OpenRouter uses the adjacent day tower.

Recommendation: best expressive alternative if the panel should feel like an instrument rather than a chart. It is honest and visually distinctive, but should be usability-tested at desktop viewing distance before committing.

Overall ranking: **Forecast Rain**, **Landing Field**, **Isometric Runway**, then **Affine Cap Map**.

Run `python3 render_variants.py` in this directory to regenerate every PNG deterministically. The script is self-contained and writes only here.
