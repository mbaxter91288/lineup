# Lineup

Picks even teams for a regular 8v8 / 9v9 football game, and keeps records of the players and the games.

When the user pastes a list of names, or asks anything about players, teams, or scores, use the **lineup** skill (`.claude/skills/lineup/SKILL.md`). It has the full flow.

Quick reference:

```bash
./bin/lineup.py resolve "Sam, Joe, Danny"      # which names are known
./bin/lineup.py list                            # every player
./bin/lineup.py balance --names "<list>" --html # even splits + team sheet page
./bin/lineup.py games                           # games and results
./bin/lineup.py squad                           # whole-squad ratings page
./bin/lineup.py edit                            # local page for editing bands
```

Data:

- `players/<uuid>/data.json` — position, ability / fitness / workrate bands, veteran level, captain flag, optional rating override, prose profile
- `games/<uuid>/data.json` — date, format, venue, bibs/non-bibs team lists, score
- `config.json` — default venue
- `schemas/` — the shape of both files
- `players/index.json` — generated lookup, rebuilt by the CLI, not edited by hand

Every time teams are generated, confirmed, or scored, the CLI rewrites the game's pages: `artifacts/teams-<date>.html` (admin, with ratings) and, once teams are confirmed, `artifacts/match-<date>.html` (shareable, no ratings anywhere in it). Publish them with the Artifact tool each time — same files, same URLs. The player page is the one to hand over when the user wants something to share.

Every stat is banded, never scored out of ten: ability, fitness and workrate each take a category, and a veteran level scales the result. The rating the balancer uses is derived from those, and only overridden by hand when it does not match how much you want the player in your team.
