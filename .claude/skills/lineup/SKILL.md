---
name: lineup
description: Generate even football teams for 8v8 and 9v9 games from a list of player names, and keep player and game records up to date. Use whenever the user pastes a list of names for a game, asks to pick or balance teams, asks about a player's rating or profile, or wants to record a score or a new player.
---

# Lineup

Turn a list of names into two even teams, using player records stored in this repository.

## Layout

- `players/<uuid>/data.json` — one file per player (`schemas/player.schema.json`)
- `players/index.json` — generated name/alias lookup, rebuilt by the CLI; never edit it by hand
- `games/<uuid>/data.json` — one file per game (`schemas/game.schema.json`)
- `bin/lineup.py` — the CLI that reads and writes all of the above

## Ratings

- `rating` is **relative to this group only**: 1 is the weakest player who turns up, 10 is the strongest. A 10 is not semi-pro; it is the best of these lads. Half points are fine.
- `fitness` is stamina over a full game, on the same relative 1–10 scale.
- `position` is one of `GK`, `DEF`, `MID`, `ATT`. Mention any second position in the profile instead.
- `profile` is prose: style of play, strengths, weaknesses, who they play well with, anything that helps future team picks.

## The main flow

When the user gives a list of names:

1. **Resolve the names.**
   ```
   ./bin/lineup.py resolve "<the pasted list>"
   ```
   Names may be comma or newline separated, with bullets or numbering; the CLI strips those.

2. **Fill the gaps.** For anyone reported `UNKNOWN`, ask the user for that player's position, rating out of 10, and fitness out of 10, plus a sentence on how they play. Ask for all unknown players in one message rather than one at a time. Remind them the rating is relative to the group if it seems useful. Then create each player:
   ```
   ./bin/lineup.py add --name "Sam" --position MID --rating 7 --fitness 6 --profile "Tidy passer, keeps the ball moving, tires in the last twenty."
   ```
   If a name is reported ambiguous, ask the user which player they meant, and add an alias so it resolves cleanly next time (`--alias "Sammy"`).

3. **Generate the teams.**
   ```
   ./bin/lineup.py balance --names "<the full list>"
   ```
   This prints the three most even splits, with each team's total rating, total fitness, and shape. Present the first option as the recommendation, and mention the alternatives briefly — the user may prefer one on a feel the numbers don't capture.

4. **Save it** once the user is happy with a split:
   ```
   ./bin/lineup.py balance --names "<the full list>" --commit
   ```
   `--commit` saves the top option. If the user picked a different option or moved players around by hand, write the game file directly instead, using `schemas/game.schema.json` and a fresh UUID.

## Recording results

After a game:
```
./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --notes "Even until the last ten minutes, bibs faded."
```
Find the id with `./bin/lineup.py games`.

Results are the feedback loop. If the user says a game was lopsided, or that someone played well above or below their rating, update that player:
```
./bin/lineup.py update Sam --rating 7.5 --profile "<revised prose>"
```
Adjust ratings in small steps — 0.5 at a time — off one performance. A rating that swings every week stops being useful for balancing. Do not change a rating without the user saying something that justifies it.

## How balancing works

`bin/lineup.py balance` searches every possible split (exhaustively up to 22 players) and scores each one on:

- total rating difference, weighted most heavily
- total fitness difference
- the difference across each team's top three players, so the best players don't stack on one side
- goalkeepers split one each when there are two
- outfield shape, so one team doesn't end up with every defender

Weights sit at the top of the script if the user wants to bias it differently.

## House rules

- Player folders are the source of truth; `players/index.json` is regenerated from them.
- The teams are always called **bibs** and **non-bibs**.
- An odd number of players is allowed — the CLI notes the uneven split and puts the extra player on the non-bibs side.
- Never invent a rating for a player you have not been given one for. Ask.
