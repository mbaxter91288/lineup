# Lineup

Picks even teams for a regular 8v8 / 9v9 football game, and keeps records of the players and the games.

When the user pastes a list of names, or asks anything about players, teams, or scores, use the **lineup** skill (`.claude/skills/lineup/SKILL.md`). It has the full flow.

Quick reference:

```bash
./bin/lineup.py resolve "Sam, Joe, Danny"      # which names are known
./bin/lineup.py list                            # every player
./bin/lineup.py balance --names "<name list>"   # three most even splits
./bin/lineup.py games                           # games and results
```

Data:

- `players/<uuid>/data.json` — position, rating (1–10, relative to this group), fitness, prose profile
- `games/<uuid>/data.json` — date, format, bibs/non-bibs team lists, score
- `schemas/` — the shape of both files
- `players/index.json` — generated lookup, rebuilt by the CLI, not edited by hand

Ratings are relative: 1 is the weakest player in the group, 10 is the strongest. 10 does not mean semi-pro.
