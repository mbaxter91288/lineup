#!/usr/bin/env python3
"""Lineup: player records and balanced team generation for 8v8 / 9v9 games.

Data lives in players/<uuid>/data.json and games/<uuid>/data.json, relative to
the repository root (the parent of this script's directory). Each game also has
a page at artifacts/teams-<date>.html, rewritten whenever the game moves on:
options generated, teams confirmed, score recorded.

Usage examples:
    ./bin/lineup.py list
    ./bin/lineup.py add --name "Sam" --position MID --rating 7 --fitness 6 --profile "Tidy passer."
    ./bin/lineup.py update Sam --rating 7.5
    ./bin/lineup.py resolve "Sam, Joe, Danny"
    ./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --html
    ./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --guest "Plus 1" --html
    ./bin/lineup.py balance --names-file tonight.txt --html --commit --date 2026-08-21
    ./bin/lineup.py games
    ./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --notes "Even until the last ten."
    ./bin/lineup.py page <game-id>
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import random
import sys
import urllib.parse
import uuid
from pathlib import Path

import render_html
import render_squad
import shape

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "players"
GAMES = ROOT / "games"
ARTIFACTS = ROOT / "artifacts"
INDEX = PLAYERS / "index.json"
CONFIG = ROOT / "config.json"
POSITIONS = ["GK", "DEF", "MID", "ATT"]
# Specific roles, for filling an 11-a-side shape. Left to right is RB/RM/RW,
# through the middle is CB/CDM/CM/CAM/ST.
ROLES = ["RB", "CB", "LB", "CDM", "CM", "CAM", "RM", "LM", "RW", "LW", "ST"]
MIDFIELD_ROLES = {"CDM", "CM", "CAM", "RM", "LM"}

# Ability is banded rather than scored out of ten: it is far easier to say what
# standard a player's game is at than to pick a number. The band covers what he
# can do and how well he reads the game - those go hand in hand - and the values
# are what the balancer works with, on the same 1-10 scale as a rating.
ABILITY_LEVELS = {
    "recreational": 3.0,   # kicks a ball about, little idea where to be
    "sunday_league": 5.0,  # knows roughly what to do and mostly does it
    "saturday": 7.0,       # reliably in the right place, uses the ball well
    "semi_pro": 9.0,       # reads the game a level above everyone else
}
ABILITY_LABELS = {
    "recreational": "Recreational",
    "sunday_league": "Sunday league",
    "saturday": "Saturday football",
    "semi_pro": "Semi-pro",
}
ABILITY_SHORT = {
    "recreational": "Rec", "sunday_league": "Sunday",
    "saturday": "Saturday", "semi_pro": "Semi-pro",
}

# Fitness is what a player has got in the tank over a full game.
FITNESS_LEVELS = {
    "low": 3.0,        # blows up early and walks a lot of it
    "moderate": 5.0,   # gets through it but fades in the last twenty
    "good": 7.0,       # runs the whole game without much dropping off
    "engine": 9.0,     # still going when everyone else has stopped
}
FITNESS_LABELS = {"low": "Low", "moderate": "Moderate", "good": "Good", "engine": "Engine"}

# Workrate is what he chooses to do with it. Not the same thing: a very fit lad
# who stands up front waiting for the ball is high fitness and low workrate.
WORKRATE_LEVELS = {
    "passenger": 3.0,   # waits for the ball, does not track back
    "steady": 5.0,      # does his share, no more
    "grafter": 7.0,     # works both ways all game
    "relentless": 9.0,  # chases everything, first to press, drags others with him
}
WORKRATE_LABELS = {"passenger": "Passenger", "steady": "Steady",
                   "grafter": "Grafter", "relentless": "Relentless"}

# Legs go before the game does, so a veteran keeps his reading of the game but
# gets less out of it. This scales the whole rating rather than knocking a flat
# amount off, so it costs a good player proportionally what it costs a poor one.
VET_LEVELS = {"none": 1.0, "veteran": 0.92, "senior": 0.78}
VET_LABELS = {"none": "", "veteran": "Vet", "senior": "Senior vet"}

# What a rating is made of. Ability carries it; legs and effort move it around.
# Named apart from the W_* cost weights below, which are a different currency.
# Ability is most of it; the weights sum to 1.0 so nothing clamps at 10.
MIX_ABILITY = 0.70
MIX_FITNESS = 0.12
MIX_WORKRATE = 0.18

# A band is a range, not a point. Its named value is the middle of it, and a
# player can be nudged either way inside the band without leaving it: two
# semi-pros are not the same player, but they are both semi-pros.
BAND_SPAN = 1.0
BAND_STEP = 0.25

# An organiser is worth something to himself and more to everyone around him.
CAPTAIN_SELF = 0.5   # added to his own rating
CAPTAIN_TEAM = 0.4   # added per team-mate when a side is being scored

# Cost weights for team balancing. Rating dominates; the rest break ties.
W_RATING = 10.0   # per point of total-rating difference
W_FITNESS = 2.0   # per point of outfield-fitness difference
W_TOP = 3.0       # per point of difference across the top 3 players
W_GK = 15.0       # per surplus permanent keeper on one side
W_SHAPE = 4.0     # per surplus outfield player of a given position
W_MIDFIELD = 6.0  # per point of difference in midfield ability
W_STAR = 6.0      # per zone left without a good player
W_CAPTAIN = 12.0  # per surplus captain on one side, when there are two or more

STAR_RATING = 8.0        # what counts as a good player for the zone check
KEEPER_FITNESS_EDGE = 2.0  # fitness advantage the side with a permanent keeper should carry,
                           # because nobody on it gets a rest in goal


# --- storage -----------------------------------------------------------------

def today() -> str:
    return dt.date.today().isoformat()


def load_config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def rebuild_index() -> dict:
    """Regenerate index.json from the player folders, which are the source of truth."""
    entries = []
    for path in sorted(PLAYERS.glob("*/data.json")):
        player = json.loads(path.read_text())
        entries.append({
            "id": player["id"],
            "name": player["name"],
            "aliases": player.get("aliases", []),
        })
    entries.sort(key=lambda e: e["name"].lower())
    index = {"players": entries}
    INDEX.write_text(json.dumps(index, indent=2) + "\n")
    return index


def load_players() -> dict[str, dict]:
    players = {}
    for path in sorted(PLAYERS.glob("*/data.json")):
        player = json.loads(path.read_text())
        players[player["id"]] = player
    return players


def save_player(player: dict) -> Path:
    folder = PLAYERS / player["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "data.json"
    path.write_text(json.dumps(player, indent=2) + "\n")
    rebuild_index()
    return path


def load_game(game_id: str) -> dict:
    path = GAMES / game_id / "data.json"
    if not path.exists():
        raise SystemExit(f"No game with id {game_id}")
    return json.loads(path.read_text())


def game_players(game: dict) -> dict[str, dict]:
    """Everyone a game can refer to: the roster, plus any guests saved on the game."""
    players = load_players()
    players.update({guest["id"]: guest for guest in game.get("guests", [])})
    return players


def load_games() -> list[dict]:
    games = [json.loads(path.read_text()) for path in sorted(GAMES.glob("*/data.json"))]
    games.sort(key=lambda g: g.get("date", ""))
    return games


def save_game(game: dict) -> Path:
    folder = GAMES / game["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "data.json"
    path.write_text(json.dumps(game, indent=2) + "\n")
    return path


def location_from(name: str | None) -> dict | None:
    """Build a location record, falling back to the default venue in config.json."""
    if name is None:
        return load_config().get("default_location")
    parts = [part.strip() for part in name.split(",")]
    location = {"name": parts[0]}
    if len(parts) > 1:
        location["town"] = parts[1]
    query = urllib.parse.quote_plus(name)
    location["maps_url"] = f"https://www.google.com/maps/search/?api=1&query={query}"
    return location


# --- name resolution ---------------------------------------------------------

def parse_names(raw: str) -> list[str]:
    """Split a name list on commas and newlines, dropping list bullets and numbering."""
    names = []
    for chunk in raw.replace("\n", ",").split(","):
        name = chunk.strip().lstrip("-*•").strip()
        while name[:1].isdigit() and "." in name[:4]:
            name = name.split(".", 1)[1].strip()
        if name:
            names.append(name)
    return names


def resolve(names: list[str], players: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Match names against known players. Returns (matched players, unknown names)."""
    matched, unknown = [], []
    for name in names:
        key = name.lower()
        hits = []
        for player in players.values():
            candidates = [player["name"].lower()] + [a.lower() for a in player.get("aliases", [])]
            if key in candidates:
                hits = [player]
                break
            if any(c.startswith(key) or key in c for c in candidates):
                hits.append(player)
        if len(hits) == 1:
            matched.append(hits[0])
        elif len(hits) > 1:
            unknown.append(f"{name} (ambiguous: {', '.join(h['name'] for h in hits)})")
        else:
            unknown.append(name)
    return matched, unknown


# --- balancing ---------------------------------------------------------------

def ability_level(player: dict) -> str:
    """The player's ability band, tolerating records written before bands existed."""
    band = player.get("ability", player.get("footballing_brain"))
    if isinstance(band, str) and band in ABILITY_LEVELS:
        return band
    score = band if isinstance(band, (int, float)) else player.get("rating", 5.0)
    for level, cutoff in (("recreational", 4.0), ("sunday_league", 6.0), ("saturday", 8.0)):
        if score <= cutoff:
            return level
    return "semi_pro"


def ability_of(player: dict) -> float:
    return band_value(player, "ability", ABILITY_LEVELS, ability_level(player))


def band_range(levels: dict, key: str) -> tuple[float, float]:
    """The lowest and highest a player can sit while still being in this band."""
    centre = levels[key]
    return (round(centre - BAND_SPAN, 2), round(centre + BAND_SPAN, 2))


def _band(player: dict, field: str, levels: dict, cutoffs: tuple) -> str:
    """Read a banded field, mapping an old out-of-ten number onto a band."""
    value = player.get(field)
    if isinstance(value, str) and value in levels:
        return value
    keys = list(levels)
    if isinstance(value, (int, float)):
        for key, cutoff in zip(keys, cutoffs):
            if value <= cutoff:
                return key
        return keys[-1]
    return keys[1]  # nothing recorded: assume the middle of the road


def fitness_level(player: dict) -> str:
    return _band(player, "fitness", FITNESS_LEVELS, (4.0, 6.0, 8.0))


def band_value(player: dict, field: str, levels: dict, key: str) -> float:
    """The band's centre, or the player's nudge within it if one is recorded."""
    low, high = band_range(levels, key)
    tweak = player.get(field + "_value")
    if isinstance(tweak, (int, float)):
        return round(min(high, max(low, float(tweak))), 2)
    return levels[key]


def fitness_of(player: dict) -> float:
    return band_value(player, "fitness", FITNESS_LEVELS, fitness_level(player))


def workrate_level(player: dict) -> str:
    return _band(player, "workrate", WORKRATE_LEVELS, (4.0, 6.0, 8.0))


def workrate_of(player: dict) -> float:
    return band_value(player, "workrate", WORKRATE_LEVELS, workrate_level(player))


def vet_level(player: dict) -> str:
    level = player.get("vet", "none")
    return level if level in VET_LEVELS else "none"


def derived_rating(player: dict) -> float:
    """Ability, legs and effort together, lifted if he organises, then aged."""
    base = (MIX_ABILITY * ability_of(player)
            + MIX_FITNESS * fitness_of(player)
            + MIX_WORKRATE * workrate_of(player))
    if player.get("captain"):
        base += CAPTAIN_SELF
    return round(max(1.0, min(10.0, base * VET_LEVELS[vet_level(player)])), 1)


def rating_of(player: dict) -> float:
    """The number the balancer works with: the override if one is set, else derived."""
    override = player.get("rating_override")
    return float(override) if override is not None else derived_rating(player)


def guest_player(name: str, squad: list[dict]) -> dict:
    """A stand-in for someone with no record, who never joins the roster. Every
    band sits at the average of the players he is turning up with, so his rating
    falls out of those like anyone else's and he tips the balance neither way."""
    guest = {
        "id": "guest-" + "-".join(name.lower().split()),
        "name": name,
        "guest": True,
        "position": "MID",
        "vet": "none",
    }
    for field, value_of, levels in (("ability", ability_of, ABILITY_LEVELS),
                                    ("fitness", fitness_of, FITNESS_LEVELS),
                                    ("workrate", workrate_of, WORKRATE_LEVELS)):
        mean = sum(value_of(p) for p in squad) / len(squad)
        value = round(mean / BAND_STEP) * BAND_STEP
        guest[field] = min(levels, key=lambda key: abs(levels[key] - value))
        guest[field + "_value"] = value
    return guest


def plays_midfield(player: dict, *, preferences: bool = True) -> bool:
    return player["position"] == "MID" or preferences and any(
        role in MIDFIELD_ROLES for role in player.get("preferred_positions", []))


def team_stats(team: list[dict]) -> dict:
    ratings = sorted((rating_of(p) for p in team), reverse=True)
    keepers = [p for p in team if p.get("permanent_keeper")]
    rating = sum(ratings)
    # An organiser gets everyone around him playing better, so his side is worth
    # more than the sum of its ratings and has to be lighter on paper to be even.
    lift = CAPTAIN_TEAM * (len(team) - 1) if any(p.get("captain") for p in team) else 0.0
    # Preferred roles only count at eleven a side; below that, a player is his position.
    full = len(team) >= shape.FULL_SIDE
    return {
        "rating": rating,
        "effective": rating + lift,
        "captain_names": [p["name"] for p in team if p.get("captain")],
        "fitness": sum(fitness_of(p) for p in team),
        # A permanent keeper does not run, so his stamina should not flatter the side.
        "outfield_fitness": sum(fitness_of(p) for p in team if not p.get("permanent_keeper")),
        "top3": sum(ratings[:3]),
        "shape": {pos: sum(1 for p in team if p["position"] == pos) for pos in POSITIONS},
        "keepers": len(keepers),
        "midfield_ability": sum(ability_of(p) for p in team if plays_midfield(p, preferences=full)),
        "captains": sum(1 for p in team if p.get("captain")),
        "stars": {
            zone: any(rating_of(p) >= STAR_RATING and shape.covers(p, zone, preferences=full) for p in team)
            for zone in ("DEF", "MID", "ATT")
        },
    }


def cost(team_a: list[dict], team_b: list[dict], gk_total: int) -> float:
    a, b = team_stats(team_a), team_stats(team_b)
    total = W_RATING * abs(a["effective"] - b["effective"])
    total += W_TOP * abs(a["top3"] - b["top3"])

    # The side with the only permanent keeper never gets a breather in goal, so
    # it should carry a little more running in it.
    edge = KEEPER_FITNESS_EDGE * (a["keepers"] - b["keepers"]) if gk_total == 1 else 0.0
    total += W_FITNESS * abs((a["outfield_fitness"] - b["outfield_fitness"]) - edge)

    if gk_total >= 2:
        total += W_GK * abs(a["keepers"] - b["keepers"])
    for pos in ("DEF", "MID", "ATT"):
        total += W_SHAPE * abs(a["shape"][pos] - b["shape"][pos])

    total += W_MIDFIELD * abs(a["midfield_ability"] - b["midfield_ability"])

    # Two captains should not end up on the same side.
    if a["captains"] + b["captains"] >= 2:
        total += W_CAPTAIN * abs(a["captains"] - b["captains"])
    for zone in ("DEF", "MID", "ATT"):
        total += W_STAR * ((not a["stars"][zone]) + (not b["stars"][zone]))
    return total


def twin_key(player: dict) -> tuple:
    """Everything the balancer and the shape can see of a player. Two players
    with the same key are interchangeable as far as a split is concerned."""
    return (player["position"], rating_of(player), ability_of(player), fitness_of(player),
            workrate_of(player), bool(player.get("captain")), bool(player.get("permanent_keeper")),
            tuple(player.get("preferred_positions", [])), tuple(player.get("negative_positions", [])))


W_GROUP = 1000.0  # steers the hill-climb away from breaking a --split group; never part of a reported cost


def lopsided(team_a: list[dict], groups: list[set[str]]) -> int:
    """How many players would have to move for every --split group to be divided
    evenly between the sides (one each for a pair, two each for four)."""
    ids = {p["id"] for p in team_a}
    moves = 0
    for group in groups:
        mine = len(group & ids)
        moves += max(0, abs(2 * mine - len(group)) - len(group) % 2) // 2
    return moves


def balance(squad: list[dict], options: int = 3, seed: int | None = None,
            groups: list[set[str]] | None = None) -> list[tuple[float, list[dict], list[dict]]]:
    """Return the most even splits, best first.

    `groups` are sets of player ids that must be divided evenly between the two
    sides; a split that leaves one lopsided is never offered.

    Small squads are enumerated exhaustively. Above that the search space gets
    too big, so it hill-climbs from random splits instead: swap the pair of
    players that helps most, repeat until no swap helps, restart, keep the best
    distinct splits found."""
    n = len(squad)
    size = n // 2  # the smaller side when the squad is odd
    gk_total = sum(1 for p in squad if p.get("permanent_keeper"))
    rng = random.Random(seed)
    found: dict[tuple, tuple[float, list[dict], list[dict]]] = {}

    # Players the numbers cannot tell apart - a guest and a placeholder, say -
    # would otherwise fill the options with one split, repeated with them swapped.
    twins: dict[tuple, str] = {}
    alike = {p["id"]: twins.setdefault(twin_key(p), p["id"]) for p in squad}

    groups = groups or []

    def priced(team_a: list[dict], team_b: list[dict]) -> float:
        return cost(team_a, team_b, gk_total) + W_GROUP * lopsided(team_a, groups)

    def record(team_a: list[dict], team_b: list[dict]) -> float:
        if lopsided(team_a, groups):
            return priced(team_a, team_b)
        score = cost(team_a, team_b, gk_total)
        key = tuple(sorted(alike[p["id"]] for p in team_a))
        mirror = tuple(sorted(alike[p["id"]] for p in team_b))
        if key not in found and mirror not in found:
            found[key] = (score, team_a, team_b)
        return score

    if n <= 18:
        anchor = squad[0]  # pin one player to avoid enumerating mirrored splits
        for combo in itertools.combinations(squad[1:], size - 1):
            team_a = [anchor] + list(combo)
            ids = {p["id"] for p in team_a}
            record(team_a, [p for p in squad if p["id"] not in ids])
    else:
        for _ in range(300):
            shuffled = squad[:]
            rng.shuffle(shuffled)
            team_a, team_b = shuffled[:size], shuffled[size:]
            current = priced(team_a, team_b)
            improved = True
            while improved:
                improved = False
                for i in range(len(team_a)):
                    for j in range(len(team_b)):
                        team_a[i], team_b[j] = team_b[j], team_a[i]
                        candidate = priced(team_a, team_b)
                        if candidate < current - 1e-9:
                            current, improved = candidate, True
                        else:
                            team_a[i], team_b[j] = team_b[j], team_a[i]
            record(list(team_a), list(team_b))

    results = sorted(found.values(), key=lambda r: (r[0], rng.random()))
    return results[:options]


def recommend(squad: list[dict], splits: list[tuple]) -> tuple[int, str]:
    """Pick the split to put forward. The maths ties often, so this breaks the tie
    on things the cost function only weighs loosely: not stacking the two weakest
    players on one team, and keeping the two strongest apart."""
    by_rating = sorted(squad, key=rating_of)
    weakest = [p["id"] for p in by_rating[:2]]
    strongest = [p["id"] for p in reversed(by_rating[-2:])]

    best_index, best_score, best_reasons = 0, None, []
    for index, (split_cost, bibs, _) in enumerate(splits):
        bib_ids = {p["id"] for p in bibs}
        weak_split = (weakest[0] in bib_ids) != (weakest[1] in bib_ids)
        strong_split = (strongest[0] in bib_ids) != (strongest[1] in bib_ids)

        score = split_cost * 0.1
        reasons = []
        if weak_split:
            reasons.append("the two weakest split one each")
        else:
            score += 3
        if strong_split:
            reasons.append("the two strongest on opposite sides")
        else:
            score += 2

        if best_score is None or score < best_score:
            best_index, best_score, best_reasons = index, score, reasons

    return best_index, ", ".join(best_reasons) if best_reasons else "the most even split on the numbers"


# --- the game pages -----------------------------------------------------------

def _meta(date: str, sizes: tuple[int, int], location: dict | None, *, title: str,
          status: str, mode: str, score: dict | None, recommended: int) -> dict:
    day = dt.date.fromisoformat(date)
    fmt = f"{sizes[0]}v{sizes[1]}"

    venue = None
    if location:
        text = location["name"]
        if location.get("town"):
            text += f", {location['town']}"
        venue = {"text": text, "maps_url": location.get("maps_url", "")}

    return {
        "title": title,
        "kicker": day.strftime("%A %-d %B"),
        "heading": f"{fmt} at {location['name']}" if location else f"{fmt} team sheet",
        "status": status,
        "venue": venue,
        "score": score,
        "recommended": recommended,
        "mode": mode,
    }


def write_options_page(splits: list[tuple], squad: list[dict], *, date: str,
                       location: dict | None, recommended: int,
                       path: Path | None = None) -> Path:
    """The admin page while the teams are still being chosen."""
    day = dt.date.fromisoformat(date)
    sizes = (len(splits[0][1]), len(splits[0][2]))
    meta = _meta(date, sizes, location,
                 title=f"{sizes[0]}v{sizes[1]} Team Sheet {day.strftime('%-d %b')}",
                 status="", mode="admin", score=None, recommended=recommended)
    path = path or ARTIFACTS / f"teams-{date}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html.render(render_html.build_payload(squad, splits, meta)))
    return path


def write_game_pages(game: dict) -> tuple[Path, Path]:
    """Both pages for a saved game: the admin sheet, and the one worth sharing.

    The player page is built from a payload with no ratings in it at all, so a
    shared link cannot expose what anyone is rated."""
    players = game_players(game)
    bibs = [players[pid] for pid in game["teams"]["bibs"] if pid in players]
    non_bibs = [players[pid] for pid in game["teams"]["non_bibs"] if pid in players]
    squad = bibs + non_bibs
    gk_total = sum(1 for p in squad if p["position"] == "GK")
    splits = [(cost(bibs, non_bibs, gk_total), bibs, non_bibs)]
    sizes = (len(bibs), len(non_bibs))
    day = dt.date.fromisoformat(game["date"])
    fmt = f"{sizes[0]}v{sizes[1]}"

    played = game["score"]["bibs"] is not None
    status = "Full time" if played else "Teams confirmed"
    score = game["score"] if played else {"bibs": 0, "non_bibs": 0}
    goals = goal_credits(game)
    lineup = game.get("lineup", {})
    location = game.get("location")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    admin_meta = _meta(game["date"], sizes, location,
                       title=f"{fmt} Team Sheet {day.strftime('%-d %b')}",
                       status=status, mode="admin", score=score, recommended=0)
    admin_path = ARTIFACTS / f"teams-{game['date']}.html"
    admin_path.write_text(render_html.render(
        render_html.build_payload(squad, splits, admin_meta, goals=goals, lineup=lineup)))

    venue_name = location["name"].split()[0] if location else "Team"
    player_meta = _meta(game["date"], sizes, location,
                        title=f"{venue_name} {fmt} {day.strftime('%-d %b')}",
                        status=status, mode="player", score=score, recommended=0)
    player_path = ARTIFACTS / f"match-{game['date']}.html"
    player_path.write_text(render_html.render(
        render_html.build_payload(squad, splits, player_meta, ratings=False,
                                  goals=goals, lineup=lineup)))

    return admin_path, player_path


def parse_scorers(entries: list[str], players: dict[str, dict], *,
                  own_goal: bool = False) -> tuple[list[dict], list[str]]:
    """Turn --scorer "Mat Baxter:2" arguments into game goal records."""
    goals, unknown = [], []
    for entry in entries:
        name, _, count = entry.rpartition(":")
        if not name:
            name, count = entry, "1"
        matched, missing = resolve([name.strip()], players)
        if missing:
            unknown.extend(missing)
            continue
        record = {"player": matched[0]["id"], "goals": int(count or 1)}
        if own_goal:
            record["own_goal"] = True
        goals.append(record)
    return goals, unknown


def goal_credits(game: dict) -> dict[str, dict]:
    """Goals per player, split into ones they meant and ones they did not."""
    credits: dict[str, dict] = {}
    for entry in game.get("goals", []):
        credit = credits.setdefault(entry["player"], {"goals": 0, "own_goals": 0})
        key = "own_goals" if entry.get("own_goal") else "goals"
        credit[key] += entry["goals"]
    return credits


def credited_score(game: dict) -> dict[str, int]:
    """What the recorded goals add up to per side. An own goal counts for the other team."""
    sides = {"bibs": 0, "non_bibs": 0}
    for entry in game.get("goals", []):
        scorer_side = "bibs" if entry["player"] in game["teams"]["bibs"] else "non_bibs"
        if entry.get("own_goal"):
            scorer_side = "non_bibs" if scorer_side == "bibs" else "bibs"
        sides[scorer_side] += entry["goals"]
    return sides


# --- rendering ---------------------------------------------------------------

def fmt_player(player: dict) -> str:
    line = f"{player['name']:<20} {player['position']:<4} rating {rating_of(player):<5} "

    line += f"{ABILITY_SHORT[ability_level(player)]:<9} "
    line += f"fit {FITNESS_LABELS[fitness_level(player)]:<9} "
    line += f"work {WORKRATE_LABELS[workrate_level(player)]:<11}"
    line += f"{VET_LABELS[vet_level(player)]:<11}"
    if player.get("rating_override") is not None:
        line += "SET "
    if player.get("captain"):
        line += "CAPTAIN "
    if player.get("permanent_keeper"):
        line += "KEEPER "
    if player.get("guest"):
        line += "GUEST "
    prefers = "/".join(player.get("preferred_positions", []))
    avoids = "/".join(player.get("negative_positions", []))
    if prefers:
        line += f" prefers {prefers}"
    if avoids:
        line += f" avoids {avoids}"
    return line


def print_split(rank: int, split: tuple[float, list[dict], list[dict]]) -> None:
    split_cost, bibs, non_bibs = split
    a, b = team_stats(bibs), team_stats(non_bibs)
    print(f"\nOption {rank}  (balance cost {split_cost:.1f}, "
          f"rating {a['rating']:.1f} v {b['rating']:.1f}, "
          f"fitness {a['fitness']:.1f} v {b['fitness']:.1f})")
    for label, team, stats in (("BIBS", bibs, a), ("NON-BIBS", non_bibs, b)):
        shape = " ".join(f"{pos}:{stats['shape'][pos]}" for pos in POSITIONS if stats["shape"][pos])
        print(f"  {label} ({len(team)}) — {shape}")
        for player in sorted(team, key=lambda p: (POSITIONS.index(p["position"]), -rating_of(p))):
            print(f"    {fmt_player(player)}")


# --- commands ----------------------------------------------------------------

def write_squad_page() -> Path:
    """Rewrite artifacts/squad.html from the player folders."""
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / "squad.html"
    path.write_text(render_squad.build(list(load_players().values())))
    return path


def cmd_squad(args) -> int:
    """Write the whole-squad ratings page, for reviewing the numbers off-game."""
    players = load_players()
    if not players:
        print("No players yet.", file=sys.stderr)
        return 1
    print(f"Squad page -> {write_squad_page()}")
    print(f"{len(players)} players. "
          f"{sum(1 for p in players.values() if p.get('rating_override') is not None)} "
          "ratings set by hand, the rest derived.")
    return 0


def cmd_edit(args) -> int:
    """Serve the band editor on localhost, writing changes to the player folders."""
    import edit_server
    return edit_server.serve(port=args.port, open_browser=not args.no_open)


def cmd_list(args) -> int:
    players = load_players()
    if not players:
        print("No players yet. Add one with: ./bin/lineup.py add --name ... --position MID "
              "--rating 6 --fitness 6 --profile '...'")
        return 0
    for player in sorted(players.values(), key=lambda p: -rating_of(p)):
        print(f"{fmt_player(player)}  {player['id']}")
    print(f"\n{len(players)} players.")
    return 0


def cmd_add(args) -> int:
    players = load_players()
    existing, _ = resolve([args.name], players)
    if existing and not args.force:
        print(f"'{args.name}' already looks like {existing[0]['name']} ({existing[0]['id']}). "
              f"Use update, or pass --force to add a separate player.", file=sys.stderr)
        return 1
    player = {
        "id": str(uuid.uuid4()),
        "name": args.name,
        "aliases": args.alias or [],
        "position": args.position,
        "preferred_positions": args.prefers or [],
        "negative_positions": args.avoids or [],
        "permanent_keeper": bool(args.permanent_keeper),
        "captain": bool(args.captain),
        "ability": args.ability,
        "vet": args.vet or "none",
        "workrate": args.workrate,
        "rating_override": args.rating,
        "fitness": args.fitness,
        "profile": args.profile,
        "created_at": today(),
        "updated_at": today(),
    }
    print(f"Added {player['name']} -> {save_player(player)}")
    return 0


def cmd_update(args) -> int:
    players = load_players()
    matched, unknown = resolve([args.name], players)
    if unknown:
        print(f"No single match for '{args.name}': {unknown[0]}", file=sys.stderr)
        return 1
    player = matched[0]
    if args.rename:
        player["name"] = args.rename
    for field in ("position", "profile"):
        value = getattr(args, field)
        if value is not None:
            player[field] = value
    if args.rating is not None:
        player["rating_override"] = args.rating
    if args.alias:
        player["aliases"] = sorted(set(player.get("aliases", []) + args.alias))
    if args.prefers:
        player["preferred_positions"] = args.prefers
    if args.avoids:
        player["negative_positions"] = args.avoids
    if args.ability is not None:
        player["ability"] = args.ability
    if args.vet is not None:
        player["vet"] = args.vet
    if args.fitness is not None:
        player["fitness"] = args.fitness
    if args.workrate is not None:
        player["workrate"] = args.workrate
    for field, levels in (("ability", ABILITY_LEVELS), ("fitness", FITNESS_LEVELS),
                          ("workrate", WORKRATE_LEVELS)):
        nudge = getattr(args, field + "_value")
        if nudge is not None:
            key = _band(player, field, levels, (4.0, 6.0, 8.0))
            low, high = band_range(levels, key)
            if not low <= nudge <= high:
                print(f"{nudge} is outside {key} ({low} to {high}).", file=sys.stderr)
                return 1
            player[field + "_value"] = nudge
    if args.clear_rating:
        player["rating_override"] = None
    if args.captain:
        player["captain"] = True
    elif args.no_captain:
        player["captain"] = False
    if args.permanent_keeper is not None:
        player["permanent_keeper"] = args.permanent_keeper
    player["updated_at"] = today()
    print(f"Updated {player['name']} -> {save_player(player)}")
    return 0


def cmd_resolve(args) -> int:
    players = load_players()
    matched, unknown = resolve(parse_names(args.names), players)
    for player in matched:
        print(f"known    {fmt_player(player)}")
    for name in unknown:
        print(f"UNKNOWN  {name}")
    return 1 if unknown else 0


def cmd_balance(args) -> int:
    raw = args.names if args.names else Path(args.names_file).read_text()
    players = load_players()
    squad, unknown = resolve(parse_names(raw), players)
    if unknown:
        print("Unknown players — add them first, then rerun:", file=sys.stderr)
        for name in unknown:
            print(f"  {name}", file=sys.stderr)
        return 1
    if len({p["id"] for p in squad}) != len(squad):
        print("The same player was listed twice.", file=sys.stderr)
        return 1
    guests = [guest_player(name, squad) for name in args.guest or []] if squad else []
    squad = squad + guests
    if len({p["id"] for p in squad}) != len(squad):
        print("The same guest was listed twice.", file=sys.stderr)
        return 1
    if len(squad) < 4:
        print("Need at least 4 players.", file=sys.stderr)
        return 1
    if len(squad) % 2:
        print(f"Note: {len(squad)} players, so the teams are uneven "
              f"({len(squad) // 2} v {len(squad) - len(squad) // 2}).")

    groups = []
    for raw_group in args.split or []:
        members, missing = resolve(parse_names(raw_group), {p["id"]: p for p in squad})
        if missing:
            print("Not in tonight's squad, so cannot be split: " + ", ".join(missing), file=sys.stderr)
            return 1
        if len(members) < 2:
            print(f"--split needs at least two players, got {raw_group!r}.", file=sys.stderr)
            return 1
        groups.append({p["id"] for p in members})

    splits = balance(squad, options=args.options, seed=args.seed, groups=groups)
    if not splits:
        print("No split keeps every --split group divided evenly.", file=sys.stderr)
        return 1
    pick, why = recommend(squad, splits)
    for rank, split in enumerate(splits, start=1):
        print_split(rank, split)
    print(f"\nRecommended: option {pick + 1} — {why}.")

    date = args.date or today()
    location = location_from(args.location)

    if args.commit:
        chosen = pick if args.pick is None else args.pick - 1
        if not 0 <= chosen < len(splits):
            print(f"There is no option {args.pick}.", file=sys.stderr)
            return 1
        _, bibs, non_bibs = splits[chosen]
        game = {
            "id": str(uuid.uuid4()),
            "date": date,
            "format": f"{len(bibs)}v{len(non_bibs)}",
            "location": location,
            "teams": {
                "bibs": [p["id"] for p in bibs],
                "non_bibs": [p["id"] for p in non_bibs],
            },
            "score": {"bibs": None, "non_bibs": None},
            "notes": "",
        }
        if guests:
            game["guests"] = guests
        print(f"\nSaved option {chosen + 1} -> {save_game(game)}")
        admin_path, player_path = write_game_pages(game)
        print(f"Admin page  -> {admin_path}")
        print(f"Player page -> {player_path}")
        print(f"Record the result later with: ./bin/lineup.py score {game['id']} --bibs N --non-bibs N")
    elif args.html is not None:
        path = Path(args.html) if args.html else None
        written = write_options_page(splits, squad, date=date, location=location,
                                     recommended=pick, path=path)
        print(f"\nPage -> {written}")
    return 0


def cmd_games(args) -> int:
    games = load_games()
    if not games:
        print("No games recorded yet.")
        return 0
    for game in games:
        players = game_players(game)
        score = game["score"]
        result = "not played" if score["bibs"] is None else f"{score['bibs']}-{score['non_bibs']}"
        venue = game.get("location", {}).get("name", "") if game.get("location") else ""
        print(f"{game['date']}  {game['format']:<6} bibs {result:<12} {venue:<18} {game['id']}")
        for label, key in (("bibs", "bibs"), ("non-bibs", "non_bibs")):
            names = [players[pid]["name"] if pid in players else f"<missing {pid}>"
                     for pid in game["teams"][key]]
            print(f"    {label:<9} {', '.join(names)}")
    return 0


def cmd_score(args) -> int:
    game = load_game(args.game_id)
    game["score"] = {"bibs": args.bibs, "non_bibs": args.non_bibs}
    if args.notes:
        game["notes"] = args.notes
    if args.scorer or args.own_goal:
        players = game_players(game)
        goals, unknown = parse_scorers(args.scorer or [], players)
        own_goals, own_unknown = parse_scorers(args.own_goal or [], players, own_goal=True)
        unknown += own_unknown
        if unknown:
            print("Unknown scorers: " + ", ".join(unknown), file=sys.stderr)
            return 1
        game["goals"] = goals + own_goals
    print(f"Recorded {args.bibs}-{args.non_bibs} -> {save_game(game)}")
    if game.get("goals"):
        credited = credited_score(game)
        if (credited["bibs"], credited["non_bibs"]) != (args.bibs, args.non_bibs):
            print(f"Note: the goals recorded add up to {credited['bibs']}-{credited['non_bibs']}, "
                  f"not {args.bibs}-{args.non_bibs}.")
    admin_path, player_path = write_game_pages(game)
    print(f"Admin page  -> {admin_path}")
    print(f"Player page -> {player_path}")
    return 0


def apply_lineup(game: dict, side: str, shape_name: str | None,
                 role_args: list[str] | None, players: dict[str, dict]) -> list[str]:
    """Pin players to roles, or set a side's shape. Returns any unknown names."""
    lineup = game.setdefault("lineup", {})
    entry = lineup.setdefault(side, {})
    if shape_name:
        entry["shape"] = shape_name
    unknown: list[str] = []
    for pair in role_args or []:
        name, _, role = pair.rpartition(":")
        role = role.strip().upper()
        matched, missing = resolve([name.strip()], players)
        if missing:
            unknown.extend(missing)
            continue
        if role not in ROLES:
            unknown.append(f"{name} (no such role: {role})")
            continue
        entry.setdefault("roles", {})[matched[0]["id"]] = role
    return unknown


def cmd_page(args) -> int:
    game = load_game(args.game_id)
    changed = False
    if args.location is not None:
        game["location"] = location_from(args.location)
        changed = True
    if args.bibs_shape or args.bibs_role or args.non_bibs_shape or args.non_bibs_role:
        players = game_players(game)
        unknown = apply_lineup(game, "bibs", args.bibs_shape, args.bibs_role, players)
        unknown += apply_lineup(game, "non_bibs", args.non_bibs_shape, args.non_bibs_role, players)
        if unknown:
            print("Could not place: " + ", ".join(unknown), file=sys.stderr)
            return 1
        changed = True
    if changed:
        save_game(game)
    admin_path, player_path = write_game_pages(game)
    print(f"Admin page  -> {admin_path}")
    print(f"Player page -> {player_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Player records and balanced teams.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list every player").set_defaults(func=cmd_list)
    sub.add_parser("squad", help="write the whole-squad ratings page").set_defaults(func=cmd_squad)
    p_edit = sub.add_parser("edit", help="edit player bands in a local browser page")
    p_edit.add_argument("--port", type=int, default=8765)
    p_edit.add_argument("--no-open", action="store_true", dest="no_open",
                        help="do not open a browser window")
    p_edit.set_defaults(func=cmd_edit)

    p_add = sub.add_parser("add", help="create a player")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--position", required=True, choices=POSITIONS)
    p_add.add_argument("--rating", type=float,
                       help="override the rating derived from ability and vet")
    p_add.add_argument("--fitness", required=True, choices=sorted(FITNESS_LEVELS),
                       help="what he has got in the tank over a full game")
    p_add.add_argument("--workrate", required=True, choices=sorted(WORKRATE_LEVELS),
                       help="what he chooses to do with it")
    p_add.add_argument("--profile", required=True)
    p_add.add_argument("--alias", action="append")
    p_add.add_argument("--prefers", action="append", choices=ROLES, metavar="ROLE",
                       help=f"preferred role, repeatable, best first ({', '.join(ROLES)})")
    p_add.add_argument("--avoids", action="append", choices=ROLES, metavar="ROLE",
                       help="role to keep this player out of, repeatable")
    p_add.add_argument("--ability", choices=sorted(ABILITY_LEVELS), required=True,
                       help="standard their game is at, reading of it included")
    p_add.add_argument("--vet", choices=sorted(VET_LEVELS),
                       help="veteran level, discounting ability for legs (default none)")
    p_add.add_argument("--captain", action="store_true",
                       help="an organiser and talker who lifts the side around him")
    p_add.add_argument("--permanent-keeper", dest="permanent_keeper", action="store_true",
                       help="a proper keeper who stays in goal all game")
    p_add.add_argument("--force", action="store_true",
                       help="add even if the name looks like an existing player")
    p_add.set_defaults(func=cmd_add)

    p_up = sub.add_parser("update", help="change a player's ratings or profile")
    p_up.add_argument("name")
    p_up.add_argument("--position", choices=POSITIONS)
    p_up.add_argument("--rating", type=float)
    p_up.add_argument("--fitness", choices=sorted(FITNESS_LEVELS))
    p_up.add_argument("--workrate", choices=sorted(WORKRATE_LEVELS))
    for field in ("ability", "fitness", "workrate"):
        p_up.add_argument(f"--{field}-value", type=float, dest=f"{field}_value",
                          help=f"nudge {field} within its band, e.g. 9.5 for a strong semi-pro")
    p_up.add_argument("--profile")
    p_up.add_argument("--alias", action="append")
    p_up.add_argument("--rename", metavar="NAME", help="change the player's name, keeping their id")
    p_up.add_argument("--prefers", action="append", choices=ROLES, metavar="ROLE",
                      help="replaces the whole preferred list, best first")
    p_up.add_argument("--avoids", action="append", choices=ROLES, metavar="ROLE",
                      help="replaces the whole avoid list")
    p_up.add_argument("--ability", choices=sorted(ABILITY_LEVELS),
                      help="standard their game is at, reading of it included")
    p_up.add_argument("--vet", choices=sorted(VET_LEVELS), help="veteran level")
    p_up.add_argument("--clear-rating", action="store_true", dest="clear_rating",
                      help="drop the manual rating and go back to the derived one")
    p_cap = p_up.add_mutually_exclusive_group()
    p_cap.add_argument("--captain", action="store_true",
                       help="an organiser and talker who lifts the side around him")
    p_cap.add_argument("--no-captain", action="store_true", dest="no_captain",
                       help="not an organiser")
    keeper = p_up.add_mutually_exclusive_group()
    keeper.add_argument("--permanent-keeper", dest="permanent_keeper", action="store_true",
                        default=None, help="stays in goal all game")
    keeper.add_argument("--rotates", dest="permanent_keeper", action="store_false",
                        help="takes a turn in goal like everyone else")
    p_up.set_defaults(func=cmd_update)

    p_res = sub.add_parser("resolve", help="check which names in a list are known")
    p_res.add_argument("names")
    p_res.set_defaults(func=cmd_resolve)

    p_bal = sub.add_parser("balance", help="generate even teams from a name list")
    group = p_bal.add_mutually_exclusive_group(required=True)
    group.add_argument("--names", help="comma or newline separated")
    group.add_argument("--names-file")
    p_bal.add_argument("--guest", action="append", metavar="NAME",
                       help='a one-off player with no record, rated at the average of the '
                            'named players and saved on the game only, e.g. --guest "Plus 1"')
    p_bal.add_argument("--split", action="append", metavar="NAMES",
                       help='players to divide evenly between the sides, repeatable: a pair goes '
                            'one each, four go two each, e.g. --split "Alex, John" '
                            '--split "Harry, Mat, Simon, Joe"')
    p_bal.add_argument("--options", type=int, default=3, help="how many splits to show (default 3)")
    p_bal.add_argument("--seed", type=int, help="tie-break seed, for reproducible output")
    p_bal.add_argument("--html", nargs="?", const="", metavar="PATH",
                       help="also write the options as a page (default artifacts/teams-<date>.html)")
    p_bal.add_argument("--commit", action="store_true",
                       help="save an option as a game, and write its page")
    p_bal.add_argument("--pick", type=int, metavar="N",
                       help="which option to commit, 1-based (default: the recommended one)")
    p_bal.add_argument("--date", help="game date, YYYY-MM-DD (default today)")
    p_bal.add_argument("--location", help='venue, e.g. "Vandyke School, Leighton Buzzard" '
                                          "(default comes from config.json)")
    p_bal.set_defaults(func=cmd_balance)

    sub.add_parser("games", help="list games and results").set_defaults(func=cmd_games)

    p_score = sub.add_parser("score", help="record the result of a game")
    p_score.add_argument("game_id")
    p_score.add_argument("--bibs", required=True, type=int)
    p_score.add_argument("--non-bibs", required=True, type=int, dest="non_bibs")
    p_score.add_argument("--notes")
    p_score.add_argument("--scorer", action="append", metavar="NAME[:GOALS]",
                         help='who scored, e.g. --scorer "Mat Baxter:2" --scorer "Lee Kent"')
    p_score.add_argument("--own-goal", action="append", metavar="NAME[:GOALS]", dest="own_goal",
                         help='who put one in their own net; it counts for the other team')
    p_score.set_defaults(func=cmd_score)

    p_page = sub.add_parser("page", help="rewrite a game's page")
    p_page.add_argument("game_id")
    p_page.add_argument("--location", help="set or change the venue first")
    p_page.add_argument("--bibs-shape", metavar="SHAPE", help='e.g. 4-5-1')
    p_page.add_argument("--bibs-role", action="append", metavar="NAME:ROLE",
                        help='pin a bibs player, e.g. --bibs-role "Mat Baxter:CDM"')
    p_page.add_argument("--non-bibs-shape", metavar="SHAPE")
    p_page.add_argument("--non-bibs-role", action="append", metavar="NAME:ROLE")
    p_page.set_defaults(func=cmd_page)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
