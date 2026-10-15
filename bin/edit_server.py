#!/usr/bin/env python3
"""A local editor for player bands, served on localhost.

The published squad page can only ever be read. This one is served from the
machine the player folders live on, so a change made in the browser is written
straight back to players/<uuid>/data.json. Nothing leaves the machine: the
server binds to the loopback address and shuts down on ctrl-c.

    ./bin/lineup.py edit
"""

from __future__ import annotations

import http.server
import json
import socketserver
import webbrowser


# Only these fields can be written, and only these values, whatever is posted.
EDITABLE = ("position", "ability", "fitness", "workrate", "vet")
BANDED = ("ability", "fitness", "workrate")   # these also carry an in-band nudge


def serve(port: int = 8765, open_browser: bool = True) -> int:
    import lineup as cli

    allowed = {
        "position": set(cli.POSITIONS),
        "ability": set(cli.ABILITY_LEVELS),
        "fitness": set(cli.FITNESS_LEVELS),
        "workrate": set(cli.WORKRATE_LEVELS),
        "vet": set(cli.VET_LEVELS),
    }

    def payload() -> dict:
        players = cli.load_players()
        rows = []
        for p in sorted(players.values(), key=lambda p: (-cli.rating_of(p), p["name"])):
            rows.append({
                "id": p["id"],
                "name": p["name"],
                "position": p["position"],
                "ability": cli.ability_level(p),
                "fitness": cli.fitness_level(p),
                "workrate": cli.workrate_level(p),
                "ability_value": cli.ability_of(p),
                "fitness_value": cli.fitness_of(p),
                "workrate_value": cli.workrate_of(p),
                "vet": cli.vet_level(p),
                "captain": bool(p.get("captain")),
                "keeper": bool(p.get("permanent_keeper")),
                "pinned": p.get("rating_override") is not None,
                "rating": cli.rating_of(p),
                "profile": p.get("profile", ""),
            })
        return {
            "rows": rows,
            "scales": {
                "ability": [{"key": k, "label": cli.ABILITY_LABELS[k], "value": v}
                            for k, v in cli.ABILITY_LEVELS.items()],
                "fitness": [{"key": k, "label": cli.FITNESS_LABELS[k], "value": v}
                            for k, v in cli.FITNESS_LEVELS.items()],
                "workrate": [{"key": k, "label": cli.WORKRATE_LABELS[k], "value": v}
                             for k, v in cli.WORKRATE_LEVELS.items()],
                "vet": [{"key": k, "label": cli.VET_LABELS[k] or "None", "value": v}
                        for k, v in cli.VET_LEVELS.items()],
                "position": [{"key": k, "label": k, "value": 0} for k in cli.POSITIONS],
            },
            "mix": {"ability": cli.MIX_ABILITY, "fitness": cli.MIX_FITNESS,
                    "workrate": cli.MIX_WORKRATE},
            "captain_self": cli.CAPTAIN_SELF,
            "span": cli.BAND_SPAN,
            "step": cli.BAND_STEP,
        }

    def apply(changes: dict) -> dict:
        """Write the posted bands back to the player folders, ignoring anything else."""
        players = cli.load_players()
        by_id = {p["id"]: p for p in players.values()}
        written = []
        for player_id, fields in changes.items():
            player = by_id.get(player_id)
            if player is None:
                continue
            touched = False
            for field in EDITABLE:
                value = fields.get(field)
                if value is not None and value in allowed[field] and player.get(field) != value:
                    player[field] = value
                    touched = True
            for field in BANDED:
                nudge = fields.get(field + "_value")
                if not isinstance(nudge, (int, float)) or isinstance(nudge, bool):
                    continue
                levels = {"ability": cli.ABILITY_LEVELS, "fitness": cli.FITNESS_LEVELS,
                          "workrate": cli.WORKRATE_LEVELS}[field]
                low, high = cli.band_range(levels, player[field])
                clamped = round(min(high, max(low, float(nudge))), 2)
                if player.get(field + "_value") != clamped:
                    player[field + "_value"] = clamped
                    touched = True
            captain = fields.get("captain")
            if isinstance(captain, bool) and bool(player.get("captain")) != captain:
                player["captain"] = captain
                touched = True
            if touched:
                player["updated_at"] = cli.today()
                cli.save_player(player)
                written.append(player["name"])
        if written:
            cli.rebuild_index()
            cli.write_squad_page()
        return {"saved": written}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - required by the base class
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            page = TEMPLATE.replace("__DATA__", json.dumps(payload()))
            self._send(page.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 - required by the base class
            if self.path != "/save":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                changes = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400, "not JSON")
                return
            if not isinstance(changes, dict):
                self.send_error(400, "expected an object")
                return
            result = apply(changes)
            result["rows"] = payload()["rows"]
            self._send(json.dumps(result).encode("utf-8"), "application/json")

        def log_message(self, *args) -> None:
            pass  # the console is for the summary line, not a request log

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"Editing {len(cli.load_players())} players at {url}")
        print("Changes save straight to players/<uuid>/data.json. Ctrl-C to stop.")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Squad Editor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Manrope:wght@400;500;600;700&display=swap">
<style>
  :root {
    --ground: #eef1ec; --surface: #ffffff; --sunk: #e6eae4; --line: #dde2d9;
    --ink: #161a15; --muted: #6c7369; --accent: #b8471f; --good: #2f6d4f;
    --band-1: #c3cbd3; --band-2: #8fa3b6; --band-3: #56789b; --band-4: #2f4f76;
    --band-1-ink: #4a5057; --band-2-ink: #33465a; --band-3-ink: #fff; --band-4-ink: #fff;
    --radius: 10px;
    --shadow: 0 1px 2px rgba(22,26,21,.05), 0 12px 30px -24px rgba(22,26,21,.5);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #111310; --surface: #1a1d19; --sunk: #232720; --line: #2c3129;
      --ink: #eef1e9; --muted: #969c92; --accent: #e2734a; --good: #67b189;
      --band-1: #3a4048; --band-2: #4c6076; --band-3: #6d92b8; --band-4: #9dbde0;
      --band-1-ink: #c3c9cf; --band-2-ink: #dbe6f0; --band-3-ink: #10161d; --band-4-ink: #10161d;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 14px 30px -26px rgba(0,0,0,.9);
    }
  }
  :root[data-theme="dark"] {
    --ground: #111310; --surface: #1a1d19; --sunk: #232720; --line: #2c3129;
    --ink: #eef1e9; --muted: #969c92; --accent: #e2734a; --good: #67b189;
    --band-1: #3a4048; --band-2: #4c6076; --band-3: #6d92b8; --band-4: #9dbde0;
    --band-1-ink: #c3c9cf; --band-2-ink: #dbe6f0; --band-3-ink: #10161d; --band-4-ink: #10161d;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 14px 30px -26px rgba(0,0,0,.9);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font-family: "Manrope", system-ui, -apple-system, sans-serif;
    font-size: 15px; line-height: 1.5; font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
  }
  .page { max-width: 1080px; margin: 0 auto; padding: 26px 18px 120px;
          display: flex; flex-direction: column; gap: 14px; }
  .card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow); }

  header { padding: 24px 24px 22px; }
  .eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .18em;
             text-transform: uppercase; color: var(--muted); margin: 0; }
  h1 { font-family: "Bricolage Grotesque", "Manrope", sans-serif;
       font-size: clamp(26px, 5vw, 36px); font-weight: 800; letter-spacing: -.03em;
       margin: 8px 0 0; }
  .standfirst { color: var(--muted); max-width: 62ch; margin: 10px 0 0; }

  .controls { padding: 14px 24px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  input[type="search"] {
    flex: 1 1 220px; min-width: 0; font: inherit; color: inherit;
    padding: 9px 13px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--sunk);
  }
  input[type="search"]:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .count { font-size: 13px; color: var(--muted); }

  .sum { padding: 22px 24px 24px; display: flex; flex-direction: column; gap: 16px; }
  .sum h2 { font-family: "Bricolage Grotesque", "Manrope", sans-serif;
            font-size: 17px; font-weight: 600; letter-spacing: -.01em; margin: 0; }
  .equation, .note { font-size: 13px; color: var(--muted); margin: 0; max-width: 68ch; }
  .equation b, .note b { color: var(--ink); font-weight: 700; }
  .scales { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 18px; }
  .scale { display: flex; flex-direction: column; gap: 6px; max-width: 260px; }
  .scale-title { font-size: 11px; font-weight: 700; letter-spacing: .14em;
                 text-transform: uppercase; color: var(--muted); margin: 0; }
  .scale-row { display: flex; align-items: center; justify-content: space-between;
               gap: 10px; font-size: 13px; }
  .scale-row .val { font-weight: 700; }
  .pill { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px;
          font-size: 12px; font-weight: 700; white-space: nowrap; }
  .pill.recreational, .pill.low, .pill.passenger { background: var(--band-1); color: var(--band-1-ink); }
  .pill.sunday_league, .pill.moderate, .pill.steady { background: var(--band-2); color: var(--band-2-ink); }
  .pill.saturday, .pill.good, .pill.grafter { background: var(--band-3); color: var(--band-3-ink); }
  .pill.semi_pro, .pill.engine, .pill.relentless { background: var(--band-4); color: var(--band-4-ink); }

  .scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 9px 8px; white-space: nowrap; }
  th:first-child, td:first-child { padding-left: 24px; }
  th:last-child, td:last-child { padding-right: 24px; }
  thead th {
    font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
    color: var(--muted); border-bottom: 1px solid var(--line);
    position: sticky; top: 0; background: var(--surface); z-index: 2;
  }
  tbody tr { border-bottom: 1px solid var(--line); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr.dirty { background: color-mix(in srgb, var(--accent) 8%, transparent); }

  .name { font-weight: 600; }
  select.plain { font-size: 12px; min-width: 68px; }

  select {
    font: inherit; font-size: 13px; font-weight: 600; color: inherit;
    padding: 6px 9px; border-radius: 7px;
    border: 1px solid var(--line); background: var(--sunk);
    cursor: pointer; max-width: 150px;
  }
  select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  select[data-field="ability"].v-recreational,
  select[data-field="fitness"].v-low,
  select[data-field="workrate"].v-passenger { background: var(--band-1); color: var(--band-1-ink); border-color: transparent; }
  select[data-field="ability"].v-sunday_league,
  select[data-field="fitness"].v-moderate,
  select[data-field="workrate"].v-steady { background: var(--band-2); color: var(--band-2-ink); border-color: transparent; }
  select[data-field="ability"].v-saturday,
  select[data-field="fitness"].v-good,
  select[data-field="workrate"].v-grafter { background: var(--band-3); color: var(--band-3-ink); border-color: transparent; }
  select[data-field="ability"].v-semi_pro,
  select[data-field="fitness"].v-engine,
  select[data-field="workrate"].v-relentless { background: var(--band-4); color: var(--band-4-ink); border-color: transparent; }

  /* --- band + nudge, the two halves of one control --- */
  .band { display: flex; flex-direction: column; gap: 5px; min-width: 132px; }
  .nudge { display: flex; align-items: center; gap: 7px; }
  .nudge input[type="range"] {
    flex: 1 1 auto; width: 78px; height: 4px; margin: 0; cursor: pointer;
    accent-color: var(--accent); background: transparent;
  }
  .nudge input[type="range"]:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
  .nudge .val {
    font-size: 12px; font-weight: 700; color: var(--muted);
    min-width: 30px; text-align: right;
  }
  .nudge .val.off { color: var(--accent); }

  .cap { display: inline-flex; align-items: center; justify-content: center; }
  input[type="checkbox"] { width: 17px; height: 17px; accent-color: var(--accent); cursor: pointer; }

  td.rating { text-align: right; font-size: 16px; font-weight: 700; }
  td.rating .was { display: block; font-size: 11px; font-weight: 600; color: var(--accent); }

  .bar {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 5;
    background: var(--surface); border-top: 1px solid var(--line);
    padding: 13px 18px; display: flex; justify-content: center;
  }
  .bar-inner { width: 100%; max-width: 1080px; display: flex; align-items: center;
               gap: 14px; flex-wrap: wrap; }
  .status { font-size: 14px; color: var(--muted); flex: 1 1 auto; }
  .status.ok { color: var(--good); font-weight: 600; }
  button {
    font: inherit; font-weight: 700; font-size: 14px; cursor: pointer;
    padding: 10px 20px; border-radius: 8px; border: none;
    background: var(--accent); color: #fff;
  }
  button.ghost { background: var(--sunk); color: var(--ink); }
  button:disabled { opacity: .45; cursor: default; }
  button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<div class="page">
  <header class="card">
    <p class="eyebrow">Local editor &middot; writes to the player folders</p>
    <h1>Squad Editor</h1>
    <p class="standfirst">
      Change a band and the rating recalculates as you go. Nothing is written until
      you press Save, and then it goes straight into
      <code>players/&lt;uuid&gt;/data.json</code> on this machine.
    </p>
  </header>

  <section class="card sum">
    <h2>How a rating is worked out</h2>
    <p class="equation" id="equation"></p>
    <div class="scales">
      <div class="scale"><p class="scale-title">Ability</p><div id="ability-scale"></div></div>
      <div class="scale"><p class="scale-title">Fitness</p><div id="fitness-scale"></div></div>
      <div class="scale"><p class="scale-title">Workrate</p><div id="workrate-scale"></div></div>
      <div class="scale"><p class="scale-title">Veteran level</p><div id="vet-scale"></div></div>
    </div>
    <p class="note" id="captain-note"></p>
  </section>

  <section class="card">
    <div class="controls">
      <input type="search" id="filter" placeholder="Find a player" autocomplete="off">
      <span class="count" id="count"></span>
    </div>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th>Player</th><th>Pos</th><th>Ability</th><th>Fitness</th>
            <th>Workrate</th><th>Vet</th><th>Capt</th>
            <th style="text-align:right">Rating</th>
          </tr>
        </thead>
        <tbody id="body"></tbody>
      </table>
    </div>
  </section>
</div>

<div class="bar">
  <div class="bar-inner">
    <span class="status" id="status">No changes yet.</span>
    <button class="ghost" id="revert" disabled>Revert</button>
    <button id="save" disabled>Save</button>
  </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById("data").textContent);
  let rows = data.rows.map(function (r) { return Object.assign({}, r); });
  let original = data.rows.map(function (r) { return Object.assign({}, r); });

  const value = function (scale, key) {
    const hit = data.scales[scale].find(function (s) { return s.key === key; });
    return hit ? hit.value : 0;
  };
  const fmt = function (n) { return Number(n).toFixed(1).replace(/\\.0$/, ""); };
  // steps are quarters, so a nudge needs two decimals before the zeros are trimmed
  const fine = function (n) {
    return Number(n).toFixed(2).replace(/0$/, "").replace(/\\.0*$/, "");
  };

  function rate(r) {
    if (r.pinned) { return r.rating; }
    let base = data.mix.ability * r.ability_value +
               data.mix.fitness * r.fitness_value +
               data.mix.workrate * r.workrate_value;
    if (r.captain) { base += data.captain_self; }
    return Math.round(Math.min(10, Math.max(1, base * value("vet", r.vet))) * 10) / 10;
  }

  function changed(r, i) {
    const o = original[i];
    return r.position !== o.position || r.ability !== o.ability || r.fitness !== o.fitness ||
           r.workrate !== o.workrate || r.vet !== o.vet || r.captain !== o.captain ||
           r.ability_value !== o.ability_value || r.fitness_value !== o.fitness_value ||
           r.workrate_value !== o.workrate_value;
  }

  function options(scale, selected) {
    return data.scales[scale].map(function (s) {
      return '<option value="' + s.key + '"' + (s.key === selected ? " selected" : "") +
             ">" + s.label + "</option>";
    }).join("");
  }

  document.getElementById("equation").innerHTML =
    "<b>" + data.mix.ability + " \u00d7 ability</b> plus <b>" + data.mix.fitness +
    " \u00d7 fitness</b> plus <b>" + data.mix.workrate + " \u00d7 workrate</b>, plus <b>" +
    data.captain_self + "</b> if he organises, then scaled by his veteran modifier and " +
    "capped at 10. Each band is a range: the slider moves a player up to " + data.span +
    " either side of its centre without leaving it.";

  document.getElementById("captain-note").innerHTML =
    "A captain is worth a further <b>0.4 per team-mate</b> when sides are being scored, " +
    "so his team has to be lighter on paper. That lift is not in the ratings here.";

  (function drawScales() {
    ["ability", "fitness", "workrate"].forEach(function (f) {
      document.getElementById(f + "-scale").innerHTML =
        data.scales[f].slice().reverse().map(function (b) {
          return '<div class="scale-row"><span class="pill ' + b.key + '">' + b.label +
                 '</span><span class="val">' + fmt(b.value) + "</span></div>";
        }).join("");
    });
    document.getElementById("vet-scale").innerHTML = data.scales.vet.map(function (v) {
      return '<div class="scale-row"><span>' + v.label + '</span><span class="val">\u00d7' +
             v.value.toFixed(2) + "</span></div>";
    }).join("");
  })();

  function render() {
    const needle = document.getElementById("filter").value.trim().toLowerCase();
    const shown = rows.filter(function (r) { return r.name.toLowerCase().includes(needle); });

    document.getElementById("body").innerHTML = shown.map(function (r) {
      const i = rows.indexOf(r);
      const now = rate(r);
      const was = changed(r, i) ? '<span class="was">was ' + fmt(original[i].rating) + "</span>" : "";
      return (
        '<tr class="' + (changed(r, i) ? "dirty" : "") + '" data-i="' + i + '">' +
          '<td><span class="name">' + r.name + "</span></td>" +
          '<td><select class="plain" data-field="position" data-i="' + i + '">' +
            options("position", r.position) + "</select></td>" +
          ["ability", "fitness", "workrate"].map(function (f) {
            const centre = value(f, r[f]);
            const now = r[f + "_value"];
            const off = Math.abs(now - centre) > 0.001;
            return '<td><span class="band">' +
              '<select data-field="' + f + '" data-i="' + i + '" class="v-' + r[f] + '">' +
                options(f, r[f]) + "</select>" +
              '<span class="nudge">' +
                '<input type="range" data-field="' + f + '_value" data-i="' + i +
                  '" min="' + (centre - data.span) + '" max="' + (centre + data.span) +
                  '" step="' + data.step + '" value="' + now +
                  '" aria-label="' + f + ' within band">' +
                '<span class="val' + (off ? " off" : "") + '">' + fine(now) + "</span>" +
              "</span></span></td>";
          }).join("") +
          '<td><select data-field="vet" data-i="' + i + '">' + options("vet", r.vet) +
            "</select></td>" +
          '<td><span class="cap"><input type="checkbox" data-field="captain" data-i="' + i +
            '"' + (r.captain ? " checked" : "") + ' aria-label="Captain"></span></td>' +
          '<td class="rating">' + fmt(now) + was + "</td>" +
        "</tr>"
      );
    }).join("");

    document.getElementById("count").textContent =
      shown.length + " of " + rows.length + " players";
    refreshFooter();
  }

  // Never re-render the table while a control is being used: rebuilding the
  // markup destroys the slider mid-drag and the gesture dies with it. Only the
  // touched row is updated, in place.
  function refreshRow(i) {
    const tr = document.querySelector('#body tr[data-i="' + i + '"]');
    if (!tr) { return; }
    const r = rows[i];

    ["ability", "fitness", "workrate"].forEach(function (f) {
      const centre = value(f, r[f]);
      const slider = tr.querySelector('input[data-field="' + f + '_value"]');
      const select = tr.querySelector('select[data-field="' + f + '"]');
      select.className = "v-" + r[f];
      slider.min = centre - data.span;
      slider.max = centre + data.span;
      if (slider.value !== String(r[f + "_value"])) { slider.value = r[f + "_value"]; }
      const label = slider.parentElement.querySelector(".val");
      label.textContent = fine(r[f + "_value"]);
      label.classList.toggle("off", Math.abs(r[f + "_value"] - centre) > 0.001);
    });

    const dirty = changed(r, i);
    tr.classList.toggle("dirty", dirty);
    tr.querySelector(".rating").innerHTML =
      fmt(rate(r)) + (dirty ? '<span class="was">was ' + fmt(original[i].rating) + "</span>" : "");
    refreshFooter();
  }

  function refreshFooter() {
    const dirty = rows.filter(changed).length;
    document.getElementById("save").disabled = dirty === 0;
    document.getElementById("revert").disabled = dirty === 0;
    const status = document.getElementById("status");
    status.className = "status";
    status.textContent = dirty === 0
      ? "No changes yet."
      : dirty + (dirty === 1 ? " player changed" : " players changed") + " and not yet saved.";
  }

  function onEdit(event) {
    const el = event.target;
    const i = Number(el.dataset.i);
    if (Number.isNaN(i)) { return; }
    const field = el.dataset.field;
    if (el.type === "checkbox") {
      rows[i][field] = el.checked;
    } else if (el.type === "range") {
      rows[i][field] = Number(el.value);
    } else {
      rows[i][field] = el.value;
      // a new band means a new range, so start from the middle of it
      if (["ability", "fitness", "workrate"].includes(field)) {
        rows[i][field + "_value"] = value(field, el.value);
      }
    }
    refreshRow(i);
  }

  document.getElementById("body").addEventListener("input", onEdit);
  document.getElementById("body").addEventListener("change", onEdit);

  document.getElementById("filter").addEventListener("input", render);

  document.getElementById("revert").addEventListener("click", function () {
    rows = original.map(function (r) { return Object.assign({}, r); });
    document.getElementById("status").className = "status";
    document.getElementById("status").textContent = "Changes discarded.";
    render();
  });

  document.getElementById("save").addEventListener("click", function () {
    const changes = {};
    rows.forEach(function (r, i) {
      if (changed(r, i)) {
        changes[r.id] = {
          position: r.position, ability: r.ability, fitness: r.fitness, workrate: r.workrate,
          vet: r.vet, captain: r.captain,
          ability_value: r.ability_value, fitness_value: r.fitness_value,
          workrate_value: r.workrate_value
        };
      }
    });
    const button = document.getElementById("save");
    const status = document.getElementById("status");
    button.disabled = true;
    status.className = "status";
    status.textContent = "Saving\\u2026";

    fetch("/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes)
    }).then(function (response) {
      if (!response.ok) { throw new Error("Server said " + response.status); }
      return response.json();
    }).then(function (result) {
      rows = result.rows.map(function (r) { return Object.assign({}, r); });
      original = result.rows.map(function (r) { return Object.assign({}, r); });
      render();
      status.className = "status ok";
      status.textContent = result.saved.length
        ? "Saved " + result.saved.join(", ") + "."
        : "Nothing needed saving.";
    }).catch(function (error) {
      status.className = "status";
      status.textContent = "Could not save: " + error.message +
        ". The server may have stopped \\u2014 check the terminal.";
      button.disabled = false;
    });
  });

  render();
</script>
</body>
</html>
"""
