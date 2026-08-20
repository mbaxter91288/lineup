# Lineup

Even teams for a weekly 8v8 / 9v9 football game.

Give Claude a list of names; it looks each one up, asks about anyone it hasn't met, and prints balanced bibs and non-bibs teams. Ratings, positions, fitness and prose profiles build up over time, and game scores feed back into them.

## Use it from the command line

```bash
./bin/lineup.py add --name "Sam" --position MID --rating 7 --fitness 6 --profile "Tidy passer, tires late."
./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --commit
./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3
```

`./bin/lineup.py --help` lists every command. No dependencies beyond Python 3.9+.

## Ratings

Relative to this group only, 1–10. 1 is the weakest player who turns up, 10 is the strongest — not a semi-pro. Fitness uses the same scale for stamina over a full game. Positions are `GK`, `DEF`, `MID`, `ATT`.

## Layout

```
players/<uuid>/data.json    one player
players/index.json          generated name lookup
games/<uuid>/data.json      one game: teams, score, notes
schemas/                    JSON schemas for both
bin/lineup.py               the CLI
.claude/skills/lineup/      the skill Claude follows
```
