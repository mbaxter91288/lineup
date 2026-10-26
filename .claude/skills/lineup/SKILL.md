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

- **Everything about a player is banded.** No stat is scored out of ten any more — pick a category and the rating falls out of it.
- **A band is a range, not a point.** Its named value is the middle, and a player can be nudged up to `BAND_SPAN` (1.0) either side without leaving the band, in steps of 0.25. Harry and Hamza can both be honestly described by their band while one is clearly better than the other. Stored as `ability_value` / `fitness_value` / `workrate_value`; absent means dead centre. Changing the band resets the nudge to the new centre. Set from the terminal with `--ability-value 9.75`, or by the slider under each dropdown in `edit`.
- `ability` — `recreational`, `sunday_league`, `saturday`, `semi_pro`. What a player can do *and* how well he reads the game; the two go hand in hand, so there is no separate footballing-brain score. Not a claim about which league he really turns out in. Scored 3 / 5 / 7 / 9.
- `fitness` — `low`, `moderate`, `good`, `engine`. What he has got in the tank over a full game. Scored 3 / 5 / 7 / 9.
- `workrate` — `passenger`, `steady`, `grafter`, `relentless`. What he chooses to do with that fitness: tracking back, pressing, covering. **Not the same as fitness** — a very fit lad who stands up front waiting for the ball is `engine` and `passenger`.
- `vet` — `none`, `veteran`, `senior`, scaling the whole rating by 1.0, 0.92 or 0.78. A multiplier rather than a flat deduction, so age costs a good player proportionally what it costs a poor one.
- **rating is derived**: `0.70 × ability + 0.12 × fitness + 0.18 × workrate` (the weights sum to 1.0, so nothing clamps at the top), plus `CAPTAIN_SELF` if he organises, all scaled by the veteran modifier. Set `--rating` only when that does not match how much you actually want the player in your team; `--clear-rating` goes back to derived. The CLI marks an overridden player `SET`.
- `position` is the general one: `GK`, `DEF`, `MID` or `ATT`. It is what the balancer uses to keep team shapes even.
- `preferred_positions` and `negative_positions` are outfield roles: `RB`, `CB`, `LB`, `CDM`, `CM`, `CAM`, `RM`, `LM`, `RW`, `LW`, `ST`. Preferred is best first; negative is roles to keep them out of whatever the shape needs. Set them with repeated `--prefers` / `--avoids` on `add` and `update`; on `update` each flag replaces the whole list.
- `captain` is a boolean for an organiser: a talker who shapes the side and gets everyone else playing better. Simon Stears is the group's one captain. He is worth `CAPTAIN_SELF` on his own rating, and when a split is scored his whole side is credited `CAPTAIN_TEAM` **per team-mate** — on a nine-a-side that is 3.2 rating points, so his team has to be clearly lighter on paper. Two captains are never left on the same side. Set it with `--captain` / `--no-captain`.
- `permanent_keeper` marks a proper goalkeeper who stays in goal all game. Everyone else rotates, so **nobody avoids going in goal** — goalkeeper is not a role in the preferred or negative lists.
- `profile` is prose: style of play, strengths, weaknesses, who they play well with, anything that helps future team picks.

## The main flow

When the user gives a list of names:

1. **Resolve the names.**
   ```
   ./bin/lineup.py resolve "<the pasted list>"
   ```
   Names may be comma or newline separated, with bullets or numbering; the CLI strips those.

2. **Fill the gaps.** For anyone reported `UNKNOWN`, ask the user for that player's position and his three bands — ability (recreational / sunday league / saturday / semi-pro), fitness (low / moderate / good / engine) and workrate (passenger / steady / grafter / relentless) — plus whether he is a veteran, plus a sentence on how they play. Ask for all unknown players in one message rather than one at a time. Then create each player:
   ```
   ./bin/lineup.py add --name "Sam" --position MID --ability saturday --fitness good --workrate grafter --profile "Tidy passer, tires in the last twenty."
   ```
   If a name is reported ambiguous, ask which player they meant and add an alias so it resolves cleanly next time (`--alias "Sammy"`).

   **Rules about who plays with whom go in `--split`.** When the user says two players cannot be on the same side, or that a group of the best players has to be shared out, pass `--split "<names>"` (repeatable) on every `balance` call, the commit included. A pair goes one each, four go two each, and a split that breaks a group is never offered. Player profiles record standing rules of this kind, so check them for the players in the list.

   **A "plus one" is not an unknown player.** When the list has a one-off the user does not want on the roster — "Plus 1", "Dave's mate" — leave him out of `--names` and pass `--guest "Plus 1"` (repeatable) on every `balance` call, the commit included. He gets ability, fitness and workrate at the average of the named players, a rating derived from those, and position `MID` with no preferred roles. He is saved on the game under `guests`, never in `players/`, and can still be scored for or pinned to a role by name.

3. **Generate the options.** Always pass `--html`:
   ```
   ./bin/lineup.py balance --names "<the full list>" --html
   ```
   Three options is the default and is usually plenty — the top splits tie on the numbers and differ only in personnel. The CLI prints each split and names a recommended option, which the page marks with a star and opens on.

4. **Publish the admin page, every time.** Call the Artifact tool on `artifacts/teams-<date>.html` with a football favicon and a one-line description, then give the user the URL:
   ```
   Artifact(file_path: "artifacts/teams-<date>.html", favicon: "⚽", description: "...")
   ```
   Every stage of a game rewrites the same files, so republishing keeps the same URLs. To update a page published in an earlier conversation, pass its URL to the Artifact tool. A different date is a different game and gets its own pair of artifacts.

5. **Say why.** Recommend an option in terms of the players rather than the numbers — who is carrying whom, whether the two weakest are split, whether the footballing brains are spread. The user may still prefer another.

6. **Confirm the teams** once the user has chosen. `--commit` saves the game and rewrites the page as the confirmed team sheet, dropping the other options:
   ```
   ./bin/lineup.py balance --names "<the full list>" --html --seed 7 --commit --pick 5
   ```
   **Always pass the same `--seed` you generated the options with.** `--commit` re-runs the balancer, and without a fixed seed the tie-break ordering shifts between runs, so `--pick 5` commits a different split from the option 5 the user was looking at. Generate with `--seed`, commit with the same `--seed`, and check the saved teams afterwards. Leave `--pick` off to commit the recommended option. This writes **both** pages — republish each of them, the player one with the 🥅 favicon, and hand the user both links, saying which is which.

## Recording results

After a game:
```
./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --notes "Even until the last ten minutes, bibs faded."
```
Add scorers with repeated `--scorer` arguments, `NAME` or `NAME:GOALS`, and own goals with `--own-goal`:
```
./bin/lineup.py score <game-id> --bibs 4 --non-bibs 3 --scorer "Mat Baxter:2" --scorer "Lee Kent" --own-goal "John Bassil"
```
An own goal is recorded against the player who scored it and credited to the other team. The CLI adds the goals up and says so if they do not match the score you gave it — check with the user rather than quietly changing either.
Find the id with `./bin/lineup.py games`. This rewrites both pages with the score in the header and a ball beside each scorer, so republish both artifacts.

Results are the feedback loop. If the user says a game was lopsided, or that someone played well above or below their rating, update that player:
```
./bin/lineup.py update Sam --rating 7.5 --profile "<revised prose>"
```
Adjust ratings in small steps — 0.5 at a time — off one performance. A general reassessment the user states outright ("Pugh is more like a 4") is not a one-game swing and can move further. A rating that swings every week stops being useful for balancing. Do not change a rating without the user saying something that justifies it.

## How balancing works

`bin/lineup.py balance` scores each possible split on:

- total rating difference, weighted most heavily
- the difference across each team's top three players, so the best players don't stack on one side
- outfield fitness, ignoring a permanent keeper's own stamina since he does not run. When only one side has a permanent keeper, that side is expected to carry a small fitness advantage, because nobody on it gets a breather in goal
- permanent keepers split one each when there are two or more
- general positions, so one team doesn't end up with every defender
- ability among the players who can play midfield
- captains: a side with one is credited `CAPTAIN_TEAM` per team-mate, so it has to be lighter on paper, and two captains are never left on the same side
- whether each team has at least one good player able to cover defence, midfield and attack

Two players the numbers cannot tell apart — a guest and a placeholder record, say — count as one split whichever way round they are, so the options are never the same teams with those two swapped.

Squads up to 18 are enumerated exhaustively; above that it hill-climbs from random splits, swapping the pair of players that helps most until nothing helps, and keeps the best distinct splits. Weights sit at the top of the script.

## Shapes and roles

`bin/shape.py` turns each team into a formation and puts every player somewhere on the pitch. **Below eleven a side, nobody is moved out of their general position**: the shape is whatever the outfield players' positions add up to (four defenders, three midfielders and an attacker play 4-3-1), and each player is only placed in a role from his own zone. Preferred roles count only at eleven a side — below that they play no part in the shape or the balancing, and a player is simply his position. The list view always shows that recorded position; the pitch shows the role. At eleven a side the team fills a 4-4-2, and because the group is defender-heavy someone usually has to play out of position there; the cost of moving a player falls as their rating rises, so the better players are the ones who shift. Either way, a role in `negative_positions` is off limits.

Whoever is in goal shows in the goalkeeper's spot. A permanent keeper is tagged `PERM`; anyone else there is just who the rotation starts with, and the untagged spot means the team rotates.

Each team attacks towards the halfway line, so on the pitch view the left-hand team's right back sits at the bottom and the right-hand team's right back sits at the top, as in any football graphic.

The user often wants to move people about after seeing the shape. `page` takes those changes and stores them on the game, so they survive every later rewrite:
```
./bin/lineup.py page <game-id> --bibs-shape 4-5-1 \
  --bibs-role "Mat Baxter:CDM" --bibs-role "Nick Bocks:CM" --bibs-role "Lee Kent:ST" \
  --non-bibs-role "Chris Stop:CB" --non-bibs-role "Luke Reddington:LB"
```
Pinned players keep their role and everyone else is fitted around them. A shape such as `4-5-1` or `3-5-2` changes the whole formation for that side. Republish both artifacts afterwards.

## The two pages

Each game has two pages, both rewritten whenever the game moves on:

- `artifacts/teams-<date>.html` — **admin.** Everything: candidate splits while teams are being chosen, then the confirmed teams with ratings, fitness and balance stats. This one stays private.
- `artifacts/match-<date>.html` — **player.** Written from the moment the teams are confirmed. Teams, positions, score and scorers, and no ratings anywhere in the file, not even in its data — this is the link the user shares with the lads, so nothing in it can embarrass anyone. Players appear on the pitch as initials rather than ratings.

Both have a table view and a pitch view, and the admin page adds a ranked view: today's squad bracketed by ability band (semi-pro down to rec), best rating first within each, numbered 1 to N, with no teams on it — for picking sides by hand. The player page never gets it. On the pitch, players animate to their new spots when the option changes, and a team with no goalkeeper puts its lowest-rated defender in goal — a visual choice only, which never changes anyone's stored position.

Never put a rating, a fitness score or a balance number on the player page, and never point the user at the admin link when they ask for something to share.

`./bin/lineup.py page <game-id>` rewrites both pages by hand if needed.

## Editing bands by hand

`./bin/lineup.py edit` serves a local page on `http://127.0.0.1:8765` and opens it. Every player is a row of dropdowns — position, ability, fitness, workrate, vet — plus a captain tick, with the rating recalculating live. The page opens with a card spelling out how a rating is worked out — the weights, every band's value and the veteran modifiers. Under each of the three banded dropdowns is a slider for nudging the player within that band; it cannot leave the band, and picking a new band re-centres it. **Save writes straight back to `players/<uuid>/data.json`** and rewrites `artifacts/squad.html`. Ctrl-C stops the server.

It only ever writes position, the three bands and their nudges, vet and captain, and only values from the enums; anything else in the request is ignored. Ratings set by hand are shown but not editable there — use `--rating` / `--clear-rating` on the CLI for those. This is the fastest way to work through the squad after a game; the CLI `update` is better for one player.

## The squad page

`./bin/lineup.py squad` writes `artifacts/squad.html`: every player on record with their band, veteran level, fitness and derived rating, the arithmetic behind each one, and their profile behind a tap. It is the page for reviewing the numbers away from a fixture. Regenerate and republish it (favicon 📋) whenever bands, veteran levels or overrides change — it does not update itself when a game page does.

## Venue

The default venue lives in `config.json` and is stamped on every game, with a Google Maps link in the page header. Override it per game with `--location "Some School, Some Town"`, on either `balance` or `page`.

## House rules

- Player folders are the source of truth; `players/index.json` is regenerated from them.
- The teams are always called **bibs** and **non-bibs**.
- Goalkeeping is taken in turns unless a genuine keeper turns up. Only set a player's position to `GK` if goalkeeper is actually their position — do not mark someone `GK` just because they spend most of the game in goal. Note that habit in their profile instead.
- An odd number of players is allowed — the CLI notes the uneven split and puts the extra player on the non-bibs side.
- Never invent a band for a player you have not been given one for. Ask.
