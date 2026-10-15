"""Turning a team into a shape: who plays where, and where that is on the pitch.

Roles are laid out on the team's own half, x running from 0 at their own goal
line to 100 at the halfway line, y from 0 at one touchline to 100 at the other.
The renderer mirrors the away half itself.
"""

from __future__ import annotations

ZONES = {
    "GK": "GK",
    "RB": "DEF", "CB": "DEF", "LB": "DEF",
    "CDM": "MID", "CM": "MID", "CAM": "MID", "RM": "MID", "LM": "MID",
    "RW": "ATT", "LW": "ATT", "ST": "ATT",
}
ZONE_ORDER = ["GK", "DEF", "MID", "ATT"]

# How far up their own half each role stands, and how wide. Central roles spread
# symmetrically when a shape asks for more than one of them.
ROLE_X = {
    "GK": 11, "CB": 23, "RB": 27, "LB": 27,
    "CDM": 44, "CM": 62, "RM": 58, "LM": 58, "CAM": 74,
    "RW": 80, "LW": 80, "ST": 86,
}
WIDE_Y = {"RB": 13, "LB": 87, "RM": 13, "LM": 87, "RW": 15, "LW": 85}


def spread(count: int) -> list[float]:
    """Symmetric y positions for `count` players in the same central role."""
    if count <= 1:
        return [50.0]
    spacing = min(30.0, 70.0 / (count - 1))
    start = 50.0 - spacing * (count - 1) / 2
    return [start + spacing * i for i in range(count)]


# The default shape for a given number of outfield players.
DEFAULT_SHAPES = {
    10: "4-4-2", 9: "4-4-1", 8: "3-3-2", 7: "3-3-1",
    6: "2-3-1", 5: "2-2-1", 4: "1-2-1", 3: "1-1-1",
}

# Which roles make up a bank of a given size.
BANKS = {
    "DEF": {1: ["CB"], 2: ["CB", "CB"], 3: ["RB", "CB", "LB"], 4: ["RB", "CB", "CB", "LB"],
            5: ["RB", "CB", "CB", "CB", "LB"]},
    "MID": {1: ["CM"], 2: ["CM", "CM"], 3: ["RM", "CM", "LM"], 4: ["CDM", "RM", "CM", "LM"],
            5: ["CDM", "RM", "CM", "CM", "LM"], 6: ["CDM", "CDM", "RM", "CM", "CM", "LM"]},
    "ATT": {1: ["ST"], 2: ["ST", "ST"], 3: ["RW", "ST", "LW"], 4: ["RW", "ST", "ST", "LW"]},
}


# Below eleven a side, nobody is moved out of their general position to fill a
# formation: the shape is whatever the players' positions add up to.
FULL_SIDE = 11
CENTRAL = {"DEF": "CB", "MID": "CM", "ATT": "ST"}


def bank(zone: str, count: int) -> list[str]:
    """The roles for a bank of `count`, widening the centre past the largest named bank."""
    if count in BANKS[zone]:
        return list(BANKS[zone][count])
    roles = list(BANKS[zone][max(BANKS[zone])])
    while len(roles) < count:
        roles.insert(len(roles) // 2, CENTRAL[zone])
    return roles


def roles_for_shape(shape: str, *, strict: bool = True) -> list[str]:
    """Turn "4-5-1" into the roles that make it up."""
    banks = [int(part) for part in shape.split("-")]
    if len(banks) != 3:
        raise ValueError(f"A shape looks like 4-4-2, not {shape!r}")
    roles = []
    for zone, count in zip(("DEF", "MID", "ATT"), banks):
        if count == 0:
            continue
        if strict and count not in BANKS[zone]:
            raise ValueError(f"No {zone} bank of {count} — pick a shape closer to eleven a side")
        roles += bank(zone, count)
    return roles


def outfield_zone(player: dict) -> str:
    """Where an outfield player plays: a goalkeeper who is not in goal drops to defence."""
    zone = player_zone(player)
    return "DEF" if zone == "GK" else zone


def shape_from_positions(outfield: list[dict], pinned: dict[str, str]) -> str:
    """The shape the players' own positions make, counting a pinned player in the
    zone of the role he has been pinned to."""
    counts = {"DEF": 0, "MID": 0, "ATT": 0}
    for p in outfield:
        counts[ZONES[pinned[p["id"]]] if p["id"] in pinned else outfield_zone(p)] += 1
    return f"{counts['DEF']}-{counts['MID']}-{counts['ATT']}"


def formation_for(count: int, shape: str | None = None) -> list[str]:
    if shape:
        roles = roles_for_shape(shape)
        if len(roles) != count:
            raise ValueError(f"Shape {shape} needs {len(roles)} outfield players, not {count}")
        return roles
    if count in DEFAULT_SHAPES:
        return roles_for_shape(DEFAULT_SHAPES[count])
    roles = roles_for_shape(DEFAULT_SHAPES[max(DEFAULT_SHAPES)])
    while len(roles) < count:
        roles.insert(len(roles) // 2, "CM")
    return roles[:count]


def player_zone(player: dict) -> str:
    return "GK" if player.get("permanent_keeper") else player["position"]


def covers(player: dict, zone: str, *, preferences: bool = True) -> bool:
    """Whether this player can be counted on in a zone, by general position or,
    at eleven a side, by a role they have said they are happy in."""
    if player_zone(player) == zone:
        return True
    return preferences and any(ZONES.get(role) == zone
                               for role in player.get("preferred_positions", []))


def role_cost(player: dict, role: str) -> float:
    """What it costs to put this player in this role. Better players are cheaper
    to move out of position, because they cope with it."""
    if role in player.get("negative_positions", []):
        return 500.0

    preferred = player.get("preferred_positions", [])
    if role in preferred:
        return preferred.index(role) * 0.6

    natural = player_zone(player)
    gap = abs(ZONE_ORDER.index(ZONES[role]) - ZONE_ORDER.index(natural)) if natural in ZONE_ORDER else 2
    same_zone_as_preference = any(ZONES.get(r) == ZONES[role] for r in preferred)
    base = 1.8 if same_zone_as_preference else 3.0 + 2.5 * gap
    # Better players cope with an unfamiliar role, so moving them costs less —
    # but never so little that the best player is the first one shunted about.
    import lineup  # deferred: lineup imports this module
    return base * (0.55 + (10 - lineup.rating_of(player)) / 12.0)


def pick_keeper(team: list[dict]) -> dict:
    """Whoever is in goal at kick-off: the permanent keeper if the team has one,
    otherwise the player the rotation would usually start with."""
    keepers = [p for p in team if p.get("permanent_keeper")]
    if keepers:
        return keepers[0]
    import lineup  # deferred: lineup imports this module
    return sorted(team, key=lambda p: (lineup.rating_of(p), lineup.fitness_of(p), p["name"]))[0]


def assign(team: list[dict], *, shape: str | None = None,
           roles_by_player: dict[str, str] | None = None) -> list[dict]:
    """Give every player a role and a spot. Returns one entry per player.

    `shape` forces a formation such as "4-5-1". `roles_by_player` pins named
    players to a role, and the rest of the shape is filled around them."""
    roles_by_player = roles_by_player or {}
    keeper = pick_keeper(team)
    outfield = [p for p in team if p["id"] != keeper["id"]]
    pinned = {p["id"]: roles_by_player[p["id"]] for p in outfield if p["id"] in roles_by_player}

    keep_zones = shape is None and len(team) < FULL_SIDE
    if keep_zones:
        roles = roles_for_shape(shape_from_positions(outfield, pinned), strict=False)
    else:
        roles = formation_for(len(outfield), shape)

    for role in pinned.values():
        if role in roles:
            roles.remove(role)
        else:
            # Free up a slot in the pinned role's own bank, or else from
            # whichever bank has most to spare.
            zone = ZONES[role]
            if not any(ZONES[r] == zone for r in roles):
                zone = max(("DEF", "MID", "ATT"),
                           key=lambda z: sum(1 for r in roles if ZONES[r] == z))
            spare = [r for r in roles if ZONES[r] == zone]
            roles.remove(spare[len(spare) // 2])
    free = [p for p in outfield if p["id"] not in pinned]

    def fit(player: dict, role: str) -> float:
        # Below eleven a side each bank holds exactly the players of that position,
        # a role outside a player's own zone is off limits, and preferred roles
        # play no part: within his bank, one role is as good as another.
        if not keep_zones:
            return role_cost(player, role)
        if ZONES[role] != outfield_zone(player):
            return 1000.0
        return 500.0 if role in player.get("negative_positions", []) else 0.0

    # Greedy on the cheapest player/role pairs, then swap pairs while it helps.
    order = sorted(
        ((fit(p, role), i, j) for i, p in enumerate(free) for j, role in enumerate(roles))
    )
    taken_players: set[int] = set()
    taken_roles: set[int] = set()
    pairing: dict[int, int] = {}
    for _, i, j in order:
        if i in taken_players or j in taken_roles:
            continue
        pairing[i] = j
        taken_players.add(i)
        taken_roles.add(j)

    improved = True
    while improved:
        improved = False
        for a in list(pairing):
            for b in list(pairing):
                if a >= b:
                    continue
                now = fit(free[a], roles[pairing[a]]) + fit(free[b], roles[pairing[b]])
                swapped = fit(free[a], roles[pairing[b]]) + fit(free[b], roles[pairing[a]])
                if swapped < now - 1e-9:
                    pairing[a], pairing[b] = pairing[b], pairing[a]
                    improved = True

    placements = [(free[i], roles[pairing[i]]) for i in pairing]
    placements += [(p, pinned[p["id"]]) for p in outfield if p["id"] in pinned]

    counts: dict[str, int] = {"GK": 1}
    for _, role in placements:
        counts[role] = counts.get(role, 0) + 1
    lanes = {role: spread(count) for role, count in counts.items()}
    used: dict[str, int] = {}

    def spot_for(role: str) -> tuple[float, float]:
        index = used.get(role, 0)
        used[role] = index + 1
        y = WIDE_Y.get(role, lanes[role][index % len(lanes[role])])
        return ROLE_X[role], y

    placed = []
    x, y = spot_for("GK")
    placed.append({
        "player": keeper,
        "role": "GK",
        "x": x,
        "y": y,
        "permanent_keeper": bool(keeper.get("permanent_keeper")),
    })

    for player, role in sorted(placements, key=lambda pair: (ZONE_ORDER.index(ZONES[pair[1]]), pair[1])):
        x, y = spot_for(role)
        placed.append({
            "player": player,
            "role": role,
            "x": x,
            "y": y,
            "permanent_keeper": False,
        })
    return placed
