"""Tournament data: the real 2026 World Cup draw and team ratings.

Groups are the final draw (December 2025, Washington D.C.), with playoff
winners resolved (March 2026). Elo ratings are from eloratings.net as of
June 2026, on the eve of the tournament.

Each team: (name, elo, confederation, is_host)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    name: str
    elo: float
    confederation: str
    is_host: bool = False


TEAMS = {
    # Group A
    "Mexico": Team("Mexico", 1875, "CONCACAF", is_host=True),
    "South Africa": Team("South Africa", 1517, "CAF"),
    "South Korea": Team("South Korea", 1758, "AFC"),
    "Czechia": Team("Czechia", 1740, "UEFA"),
    # Group B
    "Canada": Team("Canada", 1788, "CONCACAF", is_host=True),
    "Bosnia and Herzegovina": Team("Bosnia and Herzegovina", 1595, "UEFA"),
    "Qatar": Team("Qatar", 1421, "AFC"),
    "Switzerland": Team("Switzerland", 1891, "UEFA"),
    # Group C
    "Brazil": Team("Brazil", 1991, "CONMEBOL"),
    "Haiti": Team("Haiti", 1548, "CONCACAF"),
    "Morocco": Team("Morocco", 1827, "CAF"),
    "Scotland": Team("Scotland", 1782, "UEFA"),
    # Group D
    "United States": Team("United States", 1726, "CONCACAF", is_host=True),
    "Australia": Team("Australia", 1777, "AFC"),
    "Paraguay": Team("Paraguay", 1834, "CONMEBOL"),
    "Turkey": Team("Turkey", 1911, "UEFA"),
    # Group E
    "Germany": Team("Germany", 1932, "UEFA"),
    "Curacao": Team("Curacao", 1434, "CONCACAF"),
    "Ecuador": Team("Ecuador", 1938, "CONMEBOL"),
    "Ivory Coast": Team("Ivory Coast", 1695, "CAF"),
    # Group F
    "Netherlands": Team("Netherlands", 1948, "UEFA"),
    "Japan": Team("Japan", 1906, "AFC"),
    "Sweden": Team("Sweden", 1712, "UEFA"),
    "Tunisia": Team("Tunisia", 1628, "CAF"),
    # Group G
    "Belgium": Team("Belgium", 1894, "UEFA"),
    "Egypt": Team("Egypt", 1696, "CAF"),
    "Iran": Team("Iran", 1772, "AFC"),
    "New Zealand": Team("New Zealand", 1562, "OFC"),
    # Group H
    "Spain": Team("Spain", 2157, "UEFA"),
    "Cape Verde": Team("Cape Verde", 1578, "CAF"),
    "Saudi Arabia": Team("Saudi Arabia", 1576, "AFC"),
    "Uruguay": Team("Uruguay", 1892, "CONMEBOL"),
    # Group I
    "France": Team("France", 2063, "UEFA"),
    "Iraq": Team("Iraq", 1618, "AFC"),
    "Norway": Team("Norway", 1914, "UEFA"),
    "Senegal": Team("Senegal", 1860, "CAF"),
    # Group J
    "Argentina": Team("Argentina", 2114, "CONMEBOL"),
    "Algeria": Team("Algeria", 1760, "CAF"),
    "Austria": Team("Austria", 1830, "UEFA"),
    "Jordan": Team("Jordan", 1680, "AFC"),
    # Group K
    "Portugal": Team("Portugal", 1986, "UEFA"),
    "Colombia": Team("Colombia", 1982, "CONMEBOL"),
    "DR Congo": Team("DR Congo", 1652, "CAF"),
    "Uzbekistan": Team("Uzbekistan", 1714, "AFC"),
    # Group L
    "England": Team("England", 2021, "UEFA"),
    "Croatia": Team("Croatia", 1912, "UEFA"),
    "Ghana": Team("Ghana", 1510, "CAF"),
    "Panama": Team("Panama", 1730, "CONCACAF"),
}

GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Haiti", "Morocco", "Scotland"],
    "D": ["United States", "Australia", "Paraguay", "Turkey"],
    "E": ["Germany", "Curacao", "Ecuador", "Ivory Coast"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Iraq", "Norway", "Senegal"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "Colombia", "DR Congo", "Uzbekistan"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Round of 32 (matches 73-88), per the official FIFA bracket.
# Each entry: (match_no, slot_a, slot_b, feeds_r16_match)
# Slots: ("W", "E") = winner of group E, ("R", "A") = runner-up of group A,
#        ("T3", "ABCDF") = best-third from one of these groups.
ROUND_OF_32 = [
    (73, ("R", "A"), ("R", "B"), 90),
    (74, ("W", "E"), ("T3", "ABCDF"), 89),
    (75, ("W", "F"), ("R", "C"), 90),
    (76, ("W", "C"), ("R", "F"), 91),
    (77, ("W", "I"), ("T3", "CDFGH"), 89),
    (78, ("R", "E"), ("R", "I"), 91),
    (79, ("W", "A"), ("T3", "CEFHI"), 92),
    (80, ("W", "L"), ("T3", "EHIJK"), 92),
    (81, ("W", "D"), ("T3", "BEFIJ"), 94),
    (82, ("W", "G"), ("T3", "AEHIJ"), 94),
    (83, ("R", "K"), ("R", "L"), 93),
    (84, ("W", "H"), ("R", "J"), 93),
    (85, ("W", "B"), ("T3", "EFGIJ"), 96),
    (86, ("W", "J"), ("R", "H"), 95),
    (87, ("W", "K"), ("T3", "DEIJL"), 96),
    (88, ("R", "D"), ("R", "G"), 95),
]

# Round of 16 (matches 89-96): (match_no, feeder_a, feeder_b, feeds_qf)
ROUND_OF_16 = [
    (89, 74, 77, 97),
    (90, 73, 75, 97),
    (91, 76, 78, 99),
    (92, 79, 80, 99),
    (93, 83, 84, 98),
    (94, 81, 82, 98),
    (95, 86, 88, 100),
    (96, 85, 87, 100),
]

# Quarterfinals (97-100) -> Semifinals (101, 102) -> Final (104)
QUARTERFINALS = [(97, 89, 90, 101), (98, 93, 94, 101), (99, 91, 92, 102), (100, 95, 96, 102)]
SEMIFINALS = [(101, 97, 98, 104), (102, 99, 100, 104)]
