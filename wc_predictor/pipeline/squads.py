"""Scrape the 48 final squads (player, position, age, caps, intl goals, club)
from Wikipedia's '2026 FIFA World Cup squads' page into data/squads.csv."""

import re

import pandas as pd

from . import DATA_DIR, canonical
from ..data import TEAMS

SQUADS_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"
UA = {"User-Agent": "Mozilla/5.0 (wc-predictor research script)"}


def _int(text, default=0):
    m = re.search(r"\d+", str(text).replace(",", ""))
    return int(m.group()) if m else default


def scrape(force=False):
    out_path = DATA_DIR / "squads.csv"
    if out_path.exists() and not force:
        return pd.read_csv(out_path)

    import requests
    from bs4 import BeautifulSoup

    html = requests.get(SQUADS_URL, headers=UA, timeout=60).text
    soup = BeautifulSoup(html, "lxml")

    rows = []
    # Each country is a heading (h3) followed by its squad wikitable.
    for heading in soup.select("h3"):
        country = canonical(heading.get_text(strip=True).replace("[edit]", ""))
        if country not in TEAMS:
            continue
        table = heading.find_next("table", class_="wikitable")
        if table is None:
            continue
        for tr in table.select("tr")[1:]:
            cells = tr.find_all(["th", "td"])
            if len(cells) < 6:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]
            # layout: No. | Pos. | Player | DOB (age) | Caps | Goals | Club
            pos_m = re.search(r"\b(GK|DF|MF|FW)\b", texts[1])
            if not pos_m:
                continue
            player = re.sub(r"\(.*?\)", "", texts[2]).strip()
            age_m = re.search(r"aged?\s*(\d+)", texts[3], re.I)
            rows.append({
                "team": country,
                "player": player,
                "position": pos_m.group(1),
                "age": int(age_m.group(1)) if age_m else _int(texts[3][-3:], 27),
                "caps": _int(texts[4]),
                "goals": _int(texts[5]),
                "club": texts[6] if len(texts) > 6 else "",
                "captain": "captain" in texts[2].lower(),
            })

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    missing = set(TEAMS) - set(df["team"].unique())
    if missing:
        print(f"WARNING: no squad parsed for: {sorted(missing)}")
    return df
