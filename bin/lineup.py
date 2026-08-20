#!/usr/bin/env python3
"""Lineup: player records and balanced team generation for 8v8 / 9v9 games.

Data lives in players/<uuid>/data.json and games/<uuid>/data.json, relative to
the repository root (the parent of this script's directory).

Usage examples:
    ./bin/lineup.py list
    ./bin/lineup.py add --name "Sam" --position MID --rating 7 --fitness 6 --profile "Tidy passer, tires late."
    ./bin/lineup.py update Sam --rating 7.5
    ./bin/lineup.py resolve "Sam, Joe, Danny"
    ./bin/lineup.py balance --names "Sam, Joe, Danny, ..."
    ./bin/lineup.py balance --names-file tonight.txt --commit --date 2026-08-21
    ./bin/lineup.py games
    ./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --notes "Even until the last ten minutes."
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import random
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "players"
GAMES = ROOT / "games"
INDEX = PLAYERS / "index.json"
POSITIONS = ["GK", "DEF", "MID", "ATT"]

# Cost weights for team balancing. Rating dominates; the rest break ties.
W_RATING = 10.0   # per point of total-rating difference
W_FITNESS = 2.0   # per point of total-fitness difference
W_TOP = 3.0       # per point of difference across the top 3 players
W_GK = 15.0       # per surplus goalkeeper on one side
W_SHAPE = 4.0     # per surplus outfield player of a given position


# --- storage -----------------------------------------------------------------

def today() -> str:
    return dt.date.today().isoformat()


def load_index() -> dict:
    if not INDEX.exists():
        return {"players": []}
    return json.loads(INDEX.read_text())


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


def load_games() -> list[dict]:
    games = []
    for path in sorted(GAMES.glob("*/data.json")):
        games.append(json.loads(path.read_text()))
    games.sort(key=lambda g: g.get("date", ""))
    return games


def save_game(game: dict) -> Path:
    folder = GAMES / game["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "data.json"
    path.write_text(json.dumps(game, indent=2) + "\n")
    return path


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

def team_stats(team: list[dict]) -> dict:
    ratings = sorted((p["rating"] for p in team), reverse=True)
    return {
        "rating": sum(p["rating"] for p in team),
        "fitness": sum(p["fitness"] for p in team),
        "top3": sum(ratings[:3]),
        "shape": {pos: sum(1 for p in team if p["position"] == pos) for pos in POSITIONS},
    }


def cost(team_a: list[dict], team_b: list[dict], gk_total: int) -> float:
    a, b = team_stats(team_a), team_stats(team_b)
    total = W_RATING * abs(a["rating"] - b["rating"])
    total += W_FITNESS * abs(a["fitness"] - b["fitness"])
    total += W_TOP * abs(a["top3"] - b["top3"])
    if gk_total >= 2:
        total += W_GK * abs(a["shape"]["GK"] - b["shape"]["GK"])
    for pos in ("DEF", "MID", "ATT"):
        total += W_SHAPE * abs(a["shape"][pos] - b["shape"][pos])
    return total


def balance(squad: list[dict], options: int = 3, seed: int | None = None) -> list[tuple[float, list[dict], list[dict]]]:
    """Return the lowest-cost splits. Exhaustive up to 22 players, sampled above that."""
    n = len(squad)
    size = n // 2  # the smaller side when the squad is odd
    gk_total = sum(1 for p in squad if p["position"] == "GK")
    rng = random.Random(seed)
    results = []

    if n <= 22:
        anchor = squad[0]  # pin one player to avoid enumerating mirrored splits
        rest = squad[1:]
        for combo in itertools.combinations(rest, size - 1):
            team_a = [anchor] + list(combo)
            ids = {p["id"] for p in team_a}
            team_b = [p for p in squad if p["id"] not in ids]
            results.append((cost(team_a, team_b, gk_total), team_a, team_b))
    else:
        for _ in range(200_000):
            shuffled = squad[:]
            rng.shuffle(shuffled)
            team_a, team_b = shuffled[:size], shuffled[size:]
            results.append((cost(team_a, team_b, gk_total), team_a, team_b))

    results.sort(key=lambda r: (r[0], rng.random()))
    return results[:options]


# --- rendering ---------------------------------------------------------------

def fmt_player(player: dict) -> str:
    return f"{player['name']:<18} {player['position']:<4} rating {player['rating']:<4} fitness {player['fitness']}"


def print_split(rank: int, split: tuple[float, list[dict], list[dict]]) -> None:
    score, bibs, non_bibs = split
    a, b = team_stats(bibs), team_stats(non_bibs)
    print(f"\nOption {rank}  (balance cost {score:.1f}, "
          f"rating {a['rating']:.1f} v {b['rating']:.1f}, "
          f"fitness {a['fitness']:.1f} v {b['fitness']:.1f})")
    for label, team, stats in (("BIBS", bibs, a), ("NON-BIBS", non_bibs, b)):
        shape = " ".join(f"{pos}:{stats['shape'][pos]}" for pos in POSITIONS if stats["shape"][pos])
        print(f"  {label} ({len(team)}) — {shape}")
        for player in sorted(team, key=lambda p: (POSITIONS.index(p["position"]), -p["rating"])):
            print(f"    {fmt_player(player)}")


# --- commands ----------------------------------------------------------------

def cmd_list(args) -> int:
    players = load_players()
    if not players:
        print("No players yet. Add one with: ./bin/lineup.py add --name ... --position MID --rating 6 --fitness 6 --profile '...'")
        return 0
    for player in sorted(players.values(), key=lambda p: -p["rating"]):
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
        "rating": args.rating,
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
    for field in ("position", "rating", "fitness", "profile"):
        value = getattr(args, field)
        if value is not None:
            player[field] = value
    if args.alias:
        player["aliases"] = sorted(set(player.get("aliases", []) + args.alias))
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
    if len(squad) < 4:
        print("Need at least 4 players.", file=sys.stderr)
        return 1
    if len(squad) % 2:
        print(f"Note: {len(squad)} players, so the teams are uneven "
              f"({len(squad) // 2} v {len(squad) - len(squad) // 2}).")

    splits = balance(squad, options=args.options, seed=args.seed)
    for rank, split in enumerate(splits, start=1):
        print_split(rank, split)

    if args.commit:
        _, bibs, non_bibs = splits[0]
        game = {
            "id": str(uuid.uuid4()),
            "date": args.date or today(),
            "format": f"{len(bibs)}v{len(non_bibs)}",
            "teams": {
                "bibs": [p["id"] for p in bibs],
                "non_bibs": [p["id"] for p in non_bibs],
            },
            "score": {"bibs": None, "non_bibs": None},
            "notes": "",
        }
        print(f"\nSaved option 1 -> {save_game(game)}")
        print(f"Record the result later with: ./bin/lineup.py score {game['id']} --bibs N --non-bibs N")
    return 0


def cmd_games(args) -> int:
    players = load_players()
    games = load_games()
    if not games:
        print("No games recorded yet.")
        return 0
    for game in games:
        score = game["score"]
        result = "not played" if score["bibs"] is None else f"{score['bibs']}-{score['non_bibs']}"
        print(f"{game['date']}  {game['format']:<6} bibs {result:<12} {game['id']}")
        for label, key in (("bibs", "bibs"), ("non-bibs", "non_bibs")):
            names = [players[pid]["name"] if pid in players else f"<missing {pid}>"
                     for pid in game["teams"][key]]
            print(f"    {label:<9} {', '.join(names)}")
    return 0


def cmd_score(args) -> int:
    path = GAMES / args.game_id / "data.json"
    if not path.exists():
        print(f"No game with id {args.game_id}", file=sys.stderr)
        return 1
    game = json.loads(path.read_text())
    game["score"] = {"bibs": args.bibs, "non_bibs": args.non_bibs}
    if args.notes:
        game["notes"] = args.notes
    print(f"Recorded {args.bibs}-{args.non_bibs} -> {save_game(game)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Player records and balanced teams.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list every player").set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="create a player")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--position", required=True, choices=POSITIONS)
    p_add.add_argument("--rating", required=True, type=float)
    p_add.add_argument("--fitness", required=True, type=float)
    p_add.add_argument("--profile", required=True)
    p_add.add_argument("--alias", action="append")
    p_add.add_argument("--force", action="store_true", help="add even if the name looks like an existing player")
    p_add.set_defaults(func=cmd_add)

    p_up = sub.add_parser("update", help="change a player's ratings or profile")
    p_up.add_argument("name")
    p_up.add_argument("--position", choices=POSITIONS)
    p_up.add_argument("--rating", type=float)
    p_up.add_argument("--fitness", type=float)
    p_up.add_argument("--profile")
    p_up.add_argument("--alias", action="append")
    p_up.set_defaults(func=cmd_update)

    p_res = sub.add_parser("resolve", help="check which names in a list are known")
    p_res.add_argument("names")
    p_res.set_defaults(func=cmd_resolve)

    p_bal = sub.add_parser("balance", help="generate even teams from a name list")
    group = p_bal.add_mutually_exclusive_group(required=True)
    group.add_argument("--names", help="comma or newline separated")
    group.add_argument("--names-file")
    p_bal.add_argument("--options", type=int, default=3, help="how many splits to show (default 3)")
    p_bal.add_argument("--seed", type=int, help="tie-break seed, for reproducible output")
    p_bal.add_argument("--commit", action="store_true", help="save option 1 as a game")
    p_bal.add_argument("--date", help="game date, YYYY-MM-DD (default today)")
    p_bal.set_defaults(func=cmd_balance)

    sub.add_parser("games", help="list games and results").set_defaults(func=cmd_games)

    p_score = sub.add_parser("score", help="record the result of a game")
    p_score.add_argument("game_id")
    p_score.add_argument("--bibs", required=True, type=int)
    p_score.add_argument("--non-bibs", required=True, type=int, dest="non_bibs")
    p_score.add_argument("--notes")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
