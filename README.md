# Lineup

Even teams for a weekly 8v8 / 9v9 football game.

Give Claude a list of names; it looks each one up, asks about anyone it hasn't met, and prints balanced bibs and non-bibs teams. Ratings, positions, fitness and prose profiles build up over time, and game scores feed back into them.

## Use it from the command line

```bash
./bin/lineup.py add --name "Sam" --position MID --rating 7 --fitness 6 --profile "Tidy passer, tires late."
./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --html
./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --html --commit --pick 5
./bin/lineup.py balance --names "Sam, Joe, Danny, ..." --guest "Plus 1" --html   # a one-off, rated at the average, kept off the roster
./bin/lineup.py page <game-id> --bibs-shape 4-5-1 --bibs-role "Mat Baxter:CDM"
./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --scorer "Mat Baxter:2" --own-goal "John Bassil"
```

`--help` lists every command. No dependencies beyond Python 3.9+.

## The two game pages

Every game produces two pages, both rewritten as the game moves along.

**Admin** — `artifacts/teams-<date>.html`. Options to choose from, then the confirmed teams, with ratings, fitness and balance stats throughout. Keep this one to yourself.

**Player** — `artifacts/match-<date>.html`. Written once the teams are confirmed. Teams, positions, score and scorers. No ratings anywhere in it, including in the page's own data, so the link is safe to send round. On the pitch, players show as initials.

Both have a table view and a pitch view — on the pitch, players animate to their new spots as you flick between options, and whoever is standing in goal is shown there without their stored position changing. Claude publishes both as artifacts and keeps the same links as the game progresses.

Venue comes from `config.json` and appears in the header with a Google Maps link; override per game with `--location`.

## Ratings

Relative to this group only, 1–10. 1 is the weakest player who turns up, 10 is the strongest — not a semi-pro. Fitness uses the same scale for stamina over a full game.

Each player has a general position — `GK`, `DEF`, `MID`, `ATT` — plus outfield roles in `preferred_positions` and `negative_positions`, drawn from `RB`, `CB`, `LB`, `CDM`, `CM`, `CAM`, `RM`, `LM`, `RW`, `LW`, `ST`. There is also `footballing_brain`, a separate 1–10 for reading the game, which decides how midfielders are spread.

Goalkeeping is rotated, so nobody avoids it. A player marked `permanent_keeper` stays in goal all game, and the side that has one is expected to be slightly fitter, since nobody on it gets a rest in goal.

## Layout

```
players/<uuid>/data.json    one player
players/index.json          generated name lookup
games/<uuid>/data.json      one game: teams, score, notes
artifacts/teams-<date>.html the admin sheet, with ratings
artifacts/match-<date>.html the shareable page, without
schemas/                    JSON schemas for both
bin/lineup.py               the CLI
bin/render_html.py          the team sheet page renderer
.claude/skills/lineup/      the skill Claude follows
```
