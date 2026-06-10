"""Data pipeline: historical results, squads, live ESPN ingestion."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Canonical names follow wc_predictor.data; external sources get mapped.
ALIASES = {
    "Türkiye": "Turkey",
    "Czech Republic": "Czechia",
    "Curaçao": "Curacao",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
    "Côte d'Ivoire ": "Ivory Coast",
}


def canonical(name: str) -> str:
    return ALIASES.get(name.strip(), name.strip())
