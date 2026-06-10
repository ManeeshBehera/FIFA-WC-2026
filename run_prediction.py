#!/usr/bin/env python3
"""Run the full 2026 World Cup scan + Monte Carlo prediction.

Usage: python run_prediction.py [n_sims]
Writes outputs/predictions.csv and outputs/REPORT.md, prints a summary.
"""

import sys
from pathlib import Path

from wc_predictor.simulate import run, STAGE_LABELS
from wc_predictor.report import group_strength, group_match_table, dark_horses
from wc_predictor.data import GROUPS

PCT_COLS = [STAGE_LABELS[k] for k in
            ["group_win", "r32", "r16", "qf", "sf", "final", "champion"]]


def pct(x):
    return f"{100 * x:.1f}%"


def main():
    n_sims = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
    print(f"Simulating {n_sims:,} tournaments...")
    df, top_finals = run(n_sims=n_sims)

    out = Path(__file__).parent / "outputs"
    out.mkdir(exist_ok=True)
    df.to_csv(out / "predictions.csv", index=False)

    lines = []
    w = lines.append
    w("# FIFA World Cup 2026 — Tournament Scan & Prediction Report")
    w("")
    w(f"Monte Carlo simulation of the full 48-team tournament, {n_sims:,} runs.")
    w("Model: Elo-driven Poisson goals, host bonus for USA/Mexico/Canada,")
    w("exact 2026 bracket incl. best-8 third-place allocation.")
    w("")

    w("## Title odds (top 15)")
    w("")
    w("| # | Team | Group | Elo | Win group | R32 | R16 | QF | SF | Final | Champion |")
    w("|---|------|-------|-----|-----------|-----|-----|----|----|-------|----------|")
    for i, r in df.head(15).iterrows():
        cells = " | ".join(pct(r[c]) for c in PCT_COLS)
        w(f"| {i + 1} | {r['team']} | {r['group']} | {r['elo']:.0f} | {cells} |")
    w("")

    w("## Most likely finals")
    w("")
    for _, r in top_finals.iterrows():
        w(f"- {r['final']} — {pct(r['probability'])}")
    w("")

    w("## Group difficulty ranking (group of death index = avg Elo of top 3)")
    w("")
    w("| Group | Death index | Avg Elo | Teams (by Elo) |")
    w("|-------|-------------|---------|----------------|")
    for g in group_strength():
        w(f"| {g['group']} | {g['death_index']:.0f} | {g['avg_elo']:.0f} | {g['teams']} |")
    w("")

    w("## Group-by-group scan")
    for letter in GROUPS:
        w("")
        w(f"### Group {letter}")
        w("")
        sub = df[df["group"] == letter].sort_values("Reach R16", ascending=False)
        w("| Team | Elo | Win group | Reach R32 | Reach R16 | Champion |")
        w("|------|-----|-----------|-----------|-----------|----------|")
        for _, r in sub.iterrows():
            w(f"| {r['team']} | {r['elo']:.0f} | {pct(r['Win group'])} | "
              f"{pct(r['Reach R32'])} | {pct(r['Reach R16'])} | {pct(r['Champion'])} |")
        w("")
        w("| Fixture | xG | Win A | Draw | Win B |")
        w("|---------|----|-------|------|-------|")
        for m in group_match_table(letter):
            w(f"| {m['fixture']} | {m['xg']} | {pct(m['p_win_a'])} | "
              f"{pct(m['p_draw'])} | {pct(m['p_win_b'])} |")

    w("")
    w("## Dark horses (Elo < 1900 with semifinal upside)")
    w("")
    dh = dark_horses(df)
    w("| Team | Group | Elo | QF | SF | Champion |")
    w("|------|-------|-----|----|----|----------|")
    for _, r in dh.iterrows():
        w(f"| {r['team']} | {r['group']} | {r['elo']:.0f} | {pct(r['Reach QF'])} | "
          f"{pct(r['Reach SF'])} | {pct(r['Champion'])} |")

    (out / "REPORT.md").write_text("\n".join(lines))
    print(f"Wrote {out / 'predictions.csv'} and {out / 'REPORT.md'}")
    print()
    print("=== TOP 10 TITLE ODDS ===")
    for i, r in df.head(10).iterrows():
        print(f"{i + 1:>2}. {r['team']:<15} {pct(r['Champion']):>6}  "
              f"(final {pct(r['Reach Final'])}, SF {pct(r['Reach SF'])})")


if __name__ == "__main__":
    main()
