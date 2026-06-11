"""Klement-style structural layer: socioeconomic fundamentals + luck.

Inspired by Joachim Klement's World Cup model (UBS lineage; correct on
2014/2018/2022): national-team success correlates with GDP per capita
(sports infrastructure), population (talent pool), and football's
cultural status, beyond pure sporting ratings.

Our adaptation avoids double counting — Elo already embeds decades of
results, so we regress Elo on the socio factors (log-log OLS across the
48 finalists) and shrink each team a little toward its structural
expectation. Teams rated far above their fundamentals (golden
generations) give back a bit; structurally strong underperformers gain.

The second Klement ingredient, the deliberate "luck" element, lives in
simulate.run(strength_sigma=...): each simulated tournament redraws every
team's Elo from N(elo, sigma), modelling rating uncertainty rather than
just match randomness.

Socio data: approximate 2024 values (IMF/World Bank GDP per capita USD,
UN population, millions). culture is a 0-1 judgment of football's primacy
in the national sports landscape. Logs make ±20% data error negligible.
"""

import numpy as np

# team: (gdp_per_capita_usd, population_millions, football_culture_0_to_1)
SOCIO = {
    "Mexico": (13900, 130.0, 0.90),
    "South Africa": (6400, 63.0, 0.55),
    "South Korea": (34500, 51.7, 0.60),
    "Czechia": (33000, 10.5, 0.70),
    "Canada": (54000, 40.0, 0.35),
    "Bosnia and Herzegovina": (8400, 3.2, 0.85),
    "Qatar": (81000, 2.7, 0.55),
    "Switzerland": (105000, 8.8, 0.70),
    "Brazil": (10800, 211.0, 1.00),
    "Haiti": (1700, 11.7, 0.60),
    "Morocco": (4100, 37.5, 0.90),
    "Scotland": (47000, 5.5, 0.85),
    "United States": (85000, 335.0, 0.45),
    "Australia": (65000, 26.6, 0.40),
    "Paraguay": (6300, 6.9, 0.90),
    "Turkey": (13100, 85.3, 0.85),
    "Germany": (54000, 84.5, 0.90),
    "Curacao": (20000, 0.155, 0.60),
    "Ecuador": (6500, 18.0, 0.85),
    "Ivory Coast": (2700, 29.0, 0.85),
    "Netherlands": (64000, 17.9, 0.90),
    "Japan": (33900, 124.0, 0.55),
    "Sweden": (56000, 10.5, 0.70),
    "Tunisia": (4100, 12.5, 0.85),
    "Belgium": (55000, 11.8, 0.80),
    "Egypt": (3500, 106.0, 0.85),
    "Iran": (4700, 89.0, 0.80),
    "New Zealand": (48000, 5.2, 0.25),
    "Spain": (35000, 48.4, 0.95),
    "Cape Verde": (4000, 0.6, 0.70),
    "Saudi Arabia": (33000, 33.0, 0.70),
    "Uruguay": (22000, 3.4, 1.00),
    "France": (46000, 68.2, 0.85),
    "Iraq": (5900, 45.0, 0.75),
    "Norway": (90000, 5.5, 0.65),
    "Senegal": (1700, 18.0, 0.85),
    "Argentina": (13700, 46.7, 1.00),
    "Algeria": (5300, 45.6, 0.85),
    "Austria": (58000, 9.1, 0.65),
    "Jordan": (4500, 11.4, 0.65),
    "Colombia": (7000, 52.3, 0.90),
    "DR Congo": (700, 102.0, 0.75),
    "Portugal": (28000, 10.5, 0.95),
    "Uzbekistan": (2500, 36.0, 0.60),
    "Croatia": (22000, 3.85, 0.90),
    "England": (52000, 57.0, 0.95),
    "Ghana": (2300, 34.0, 0.85),
    "Panama": (19000, 4.5, 0.60),
}


def structural_fit(elo_by_team):
    """OLS: elo ~ ln(gdp pc) + ln(pop) + culture across the 48 finalists.

    Returns (predicted_elo_by_team, r_squared, coefs).
    """
    names = [n for n in elo_by_team if n in SOCIO]
    X = np.array([[1.0, np.log(SOCIO[n][0]), np.log(SOCIO[n][1]), SOCIO[n][2]]
                  for n in names])
    y = np.array([elo_by_team[n] for n in names])
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coefs
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot
    return dict(zip(names, pred)), r2, coefs


def klement_adjust(elo_by_team, shrink=0.15):
    """Shrink ratings toward structural expectation.

    adjusted = (1-shrink)*elo + shrink*structural_elo. Returns
    (adjusted_by_team, diagnostics) where diagnostics lists the biggest
    over/under-performers vs fundamentals.
    """
    pred, r2, _ = structural_fit(elo_by_team)
    adjusted, residuals = {}, {}
    for n, e in elo_by_team.items():
        p = pred.get(n, e)
        adjusted[n] = (1.0 - shrink) * e + shrink * p
        residuals[n] = e - p
    order = sorted(residuals, key=residuals.get)
    diagnostics = {
        "r_squared": round(r2, 3),
        "underperformers": [(n, round(residuals[n])) for n in order[:5]],
        "overperformers": [(n, round(residuals[n])) for n in order[-5:][::-1]],
    }
    return adjusted, diagnostics
