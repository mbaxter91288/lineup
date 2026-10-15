#!/usr/bin/env python3
"""Render the whole squad as a reviewable ratings page.

Unlike the game pages this one is not tied to a fixture: it lists every player
on record with the band, veteran level and fitness that produce their rating,
so the numbers can be checked and argued with. Written to artifacts/squad.html.
"""

from __future__ import annotations

import datetime as dt
import json


def build(players: list[dict]) -> str:
    import lineup as cli

    rows = []
    for p in sorted(players, key=lambda p: (-cli.rating_of(p), p["name"])):
        band = cli.ability_level(p)
        vet = cli.vet_level(p)
        rows.append({
            "name": p["name"],
            "position": p["position"],
            "band": band,
            "band_label": cli.ABILITY_LABELS[band],
            "band_value": cli.ability_of(p),
            "vet": vet,
            "vet_label": cli.VET_LABELS[vet],
            "vet_modifier": cli.VET_LEVELS[vet],
            "fitness": cli.fitness_level(p),
            "fitness_label": cli.FITNESS_LABELS[cli.fitness_level(p)],
            "fitness_value": cli.fitness_of(p),
            "band_centre": cli.ABILITY_LEVELS[band],
            "workrate": cli.workrate_level(p),
            "workrate_label": cli.WORKRATE_LABELS[cli.workrate_level(p)],
            "workrate_value": cli.workrate_of(p),
            "rating": cli.rating_of(p),
            "derived": cli.derived_rating(p),
            "pinned": p.get("rating_override") is not None,
            "captain": bool(p.get("captain")),
            "keeper": bool(p.get("permanent_keeper")),
            "profile": p.get("profile", ""),
        })

    counts = {b: sum(1 for r in rows if r["band"] == b) for b in cli.ABILITY_LEVELS}
    payload = {
        "rows": rows,
        "counts": counts,
        "bands": [{"key": k, "label": cli.ABILITY_LABELS[k], "value": v}
                  for k, v in cli.ABILITY_LEVELS.items()],
        "fitness_bands": [{"key": k, "label": cli.FITNESS_LABELS[k], "value": v}
                          for k, v in cli.FITNESS_LEVELS.items()],
        "workrate_bands": [{"key": k, "label": cli.WORKRATE_LABELS[k], "value": v}
                           for k, v in cli.WORKRATE_LEVELS.items()],
        "vets": [{"key": k, "label": cli.VET_LABELS[k] or "None", "modifier": v}
                 for k, v in cli.VET_LEVELS.items()],
        "mix": {"ability": cli.MIX_ABILITY, "fitness": cli.MIX_FITNESS,
                "workrate": cli.MIX_WORKRATE},
        "captain_self": cli.CAPTAIN_SELF,
        "captain_team": cli.CAPTAIN_TEAM,
        "updated": dt.date.today().strftime("%-d %B %Y"),
        "captains": sum(1 for r in rows if r["captain"]),
        "vets_count": sum(1 for r in rows if r["vet"] != "none"),
        "pinned": sum(1 for r in rows if r["pinned"]),
    }
    return TEMPLATE.replace("__DATA__", json.dumps(payload))


TEMPLATE = """<title>Thursday Squad</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Manrope:wght@400;500;600;700&display=swap">
<style>
  :root {
    --ground: #eef1ec;
    --surface: #ffffff;
    --sunk: #e6eae4;
    --line: #dde2d9;
    --ink: #161a15;
    --muted: #6c7369;
    --accent: #b8471f;
    --band-1: #c3cbd3;
    --band-2: #8fa3b6;
    --band-3: #56789b;
    --band-4: #2f4f76;
    --band-1-ink: #4a5057;
    --band-2-ink: #33465a;
    --band-3-ink: #ffffff;
    --band-4-ink: #ffffff;
    --radius: 10px;
    --shadow: 0 1px 2px rgba(22, 26, 21, .05), 0 12px 30px -24px rgba(22, 26, 21, .5);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #111310;
      --surface: #1a1d19;
      --sunk: #232720;
      --line: #2c3129;
      --ink: #eef1e9;
      --muted: #969c92;
      --accent: #e2734a;
      --band-1: #3a4048;
      --band-2: #4c6076;
      --band-3: #6d92b8;
      --band-4: #9dbde0;
      --band-1-ink: #c3c9cf;
      --band-2-ink: #dbe6f0;
      --band-3-ink: #10161d;
      --band-4-ink: #10161d;
      --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 14px 30px -26px rgba(0, 0, 0, .9);
    }
  }
  :root[data-theme="dark"] {
    --ground: #111310;
    --surface: #1a1d19;
    --sunk: #232720;
    --line: #2c3129;
    --ink: #eef1e9;
    --muted: #969c92;
    --accent: #e2734a;
    --band-1: #3a4048;
    --band-2: #4c6076;
    --band-3: #6d92b8;
    --band-4: #9dbde0;
    --band-1-ink: #c3c9cf;
    --band-2-ink: #dbe6f0;
    --band-3-ink: #10161d;
    --band-4-ink: #10161d;
    --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 14px 30px -26px rgba(0, 0, 0, .9);
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.5;
    font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
  }

  .page {
    max-width: 940px;
    margin: 0 auto;
    padding: 30px 18px 72px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .card {
    background: var(--surface);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }

  /* --- masthead --- */
  header { padding: 28px 26px 26px; display: flex; flex-direction: column; gap: 18px; }
  .eyebrow {
    font-size: 11px; font-weight: 700; letter-spacing: .18em;
    text-transform: uppercase; color: var(--muted);
  }
  h1 {
    font-family: "Bricolage Grotesque", "Manrope", sans-serif;
    font-size: clamp(30px, 6vw, 44px); font-weight: 800;
    letter-spacing: -.03em; line-height: 1.02;
    margin: 8px 0 0; text-wrap: balance;
  }
  .standfirst { color: var(--muted); max-width: 58ch; margin: 12px 0 0; }

  .tallies { display: flex; flex-wrap: wrap; gap: 10px; }
  .tally {
    display: flex; align-items: baseline; gap: 8px;
    padding: 9px 14px; border-radius: 8px; background: var(--sunk);
  }
  .tally b { font-size: 18px; font-weight: 700; }
  .tally span { font-size: 12px; font-weight: 600; color: var(--muted); letter-spacing: .04em; }

  /* --- the sum --- */
  .sum { padding: 22px 26px 24px; display: flex; flex-direction: column; gap: 16px; }
  .sum h2, .table-wrap h2 {
    font-family: "Bricolage Grotesque", "Manrope", sans-serif;
    font-size: 17px; font-weight: 600; letter-spacing: -.01em; margin: 0;
  }
  .scales { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 18px; }
  .scale { display: flex; flex-direction: column; gap: 7px; max-width: 280px; }
  .scale-title {
    font-size: 11px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--muted);
  }
  .scale-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 14px; }
  .scale-row .val { font-weight: 700; }
  .note { font-size: 13px; color: var(--muted); margin: 0; max-width: 66ch; }
  .equation { font-size: 14px; color: var(--muted); margin: 0; max-width: 66ch; }
  .equation b { color: var(--ink); font-weight: 700; }

  .pill {
    display: inline-flex; align-items: center;
    padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 700; letter-spacing: .02em; white-space: nowrap;
  }
  .pill.recreational  { background: var(--band-1); color: var(--band-1-ink); }
  .pill.sunday_league { background: var(--band-2); color: var(--band-2-ink); }
  .pill.saturday      { background: var(--band-3); color: var(--band-3-ink); }
  .pill.semi_pro      { background: var(--band-4); color: var(--band-4-ink); }
  .pill.low, .pill.passenger    { background: var(--band-1); color: var(--band-1-ink); }
  .pill.moderate, .pill.steady  { background: var(--band-2); color: var(--band-2-ink); }
  .pill.good, .pill.grafter     { background: var(--band-3); color: var(--band-3-ink); }
  .pill.engine, .pill.relentless { background: var(--band-4); color: var(--band-4-ink); }

  /* --- table --- */
  .table-wrap { padding: 22px 0 8px; display: flex; flex-direction: column; gap: 14px; }
  .table-wrap h2, .hint { padding: 0 26px; }
  .hint { font-size: 13px; color: var(--muted); margin: -6px 0 0; }
  .scroll { overflow-x: auto; }

  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 11px 10px; white-space: nowrap; }
  th:first-child, td:first-child { padding-left: 26px; }
  th:last-child, td:last-child { padding-right: 26px; }
  thead th {
    font-size: 11px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: var(--muted);
    border-bottom: 1px solid var(--line);
    position: sticky; top: 0; background: var(--surface); z-index: 1;
  }
  thead th button {
    font: inherit; color: inherit; letter-spacing: inherit; text-transform: inherit;
    background: none; border: none; padding: 0; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px;
  }
  thead th button:hover { color: var(--ink); }
  thead th button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 3px; }
  thead th .arrow { opacity: 0; font-size: 9px; }
  thead th[aria-sort] .arrow { opacity: 1; }
  th.num, td.num { text-align: right; }

  tbody tr { border-bottom: 1px solid var(--line); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr.open { background: var(--sunk); }
  tbody tr.player { cursor: pointer; }
  tbody tr.player:hover { background: var(--sunk); }

  .who { display: flex; align-items: center; gap: 8px; }
  .who .name { font-weight: 600; }
  .tag {
    font-size: 10px; font-weight: 700; letter-spacing: .06em;
    padding: 2px 6px; border-radius: 4px;
  }
  .tag.captain { background: var(--accent); color: #fff; }
  .tag.keeper { background: var(--sunk); color: var(--muted); border: 1px solid var(--line); }
  tr.open .tag.keeper { background: var(--surface); }
  .pos { font-size: 12px; font-weight: 600; color: var(--muted); }
  .vet-cell { font-size: 13px; color: var(--muted); }
  .rating { font-size: 17px; font-weight: 700; }

  .bar { display: flex; align-items: center; justify-content: flex-end; gap: 9px; }
  .bar .track {
    width: 62px; height: 5px; border-radius: 3px;
    background: var(--sunk); overflow: hidden;
  }
  .bar .fill { display: block; height: 100%; background: var(--band-3); border-radius: 3px; }

  tr.detail td { padding: 0 26px 18px; white-space: normal; background: var(--sunk); }
  tr.detail .profile { color: var(--muted); max-width: 68ch; font-size: 14px; margin: 0; }
  tr.detail .maths { font-size: 13px; color: var(--muted); margin: 10px 0 0; }
  tr.detail .maths b { color: var(--ink); }

  footer { padding: 0 8px; color: var(--muted); font-size: 13px; }

  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
</style>

<div class="page">
  <header class="card">
    <div>
      <p class="eyebrow" id="updated"></p>
      <h1>Thursday Squad</h1>
      <p class="standfirst">
        Every player on record, and the arithmetic behind the number the balancer uses.
        Nobody is scored out of ten: ability, fitness and workrate are each a band, and
        the rating falls out of them. Tap a row for the profile and the sum.
      </p>
    </div>
    <div class="tallies" id="tallies"></div>
  </header>

  <section class="card sum">
    <h2>How a rating is worked out</h2>
    <p class="equation" id="equation"></p>
    <div class="scales">
      <div class="scale">
        <p class="scale-title">Ability band</p>
        <div id="band-scale"></div>
      </div>
      <div class="scale">
        <p class="scale-title">Fitness</p>
        <div id="fitness-scale"></div>
      </div>
      <div class="scale">
        <p class="scale-title">Workrate</p>
        <div id="workrate-scale"></div>
      </div>
      <div class="scale">
        <p class="scale-title">Veteran level</p>
        <div id="vet-scale"></div>
      </div>
    </div>
    <p class="note" id="captain-note"></p>
  </section>

  <section class="card table-wrap">
    <h2>The squad</h2>
    <p class="hint" id="hint"></p>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th><button data-sort="name">Player <span class="arrow">&#9660;</span></button></th>
            <th><button data-sort="position">Pos <span class="arrow">&#9660;</span></button></th>
            <th><button data-sort="band_value">Ability <span class="arrow">&#9660;</span></button></th>
            <th><button data-sort="fitness_value">Fitness <span class="arrow">&#9660;</span></button></th>
            <th><button data-sort="workrate_value">Workrate <span class="arrow">&#9660;</span></button></th>
            <th><button data-sort="vet_modifier">Vet <span class="arrow">&#9660;</span></button></th>
            <th class="num"><button data-sort="rating">Rating <span class="arrow">&#9660;</span></button></th>
          </tr>
        </thead>
        <tbody id="body"></tbody>
      </table>
    </div>
  </section>

  <footer>
    <p>Every band here is a judgement call, not a measurement. Argue with them: that is
    what this page is for.</p>
  </footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById("data").textContent);
  let sortKey = "rating";
  let sortDown = true;

  const fmt = function (n) { return Number(n).toFixed(1).replace(/\\.0$/, ""); };

  document.getElementById("updated").textContent = "Updated " + data.updated;

  document.getElementById("hint").textContent =
    data.pinned === 0
      ? "Every rating on this page is derived. None have been set by hand."
      : data.pinned + " of " + data.rows.length + " ratings are set by hand rather than derived.";

  document.getElementById("tallies").innerHTML =
    data.bands.slice().reverse().map(function (b) {
      return '<div class="tally"><b>' + (data.counts[b.key] || 0) + "</b><span>" +
             b.label + "</span></div>";
    }).join("") +
    '<div class="tally"><b>' + data.vets_count + "</b><span>Veterans</span></div>" +
    '<div class="tally"><b>' + data.captains + "</b><span>Captains</span></div>";

  const mix = data.mix;
  document.getElementById("equation").innerHTML =
    "A rating is <b>" + mix.ability + " \u00d7 ability</b> plus <b>" + mix.fitness +
    " \u00d7 fitness</b> plus <b>" + mix.workrate + " \u00d7 workrate</b>, plus <b>" +
    data.captain_self + "</b> if he organises, and the whole thing is then scaled by his " +
    "veteran modifier.";

  document.getElementById("captain-note").innerHTML =
    "A captain is also worth <b>" + data.captain_team +
    "</b> per team-mate when sides are being scored, so his team has to be lighter on paper " +
    "for the game to come out even. That lift does not show in the ratings below.";

  function scale(id, bands) {
    document.getElementById(id).innerHTML = bands.slice().reverse().map(function (b) {
      return '<div class="scale-row"><span class="pill ' + b.key + '">' + b.label +
             '</span><span class="val">' + fmt(b.value) + "</span></div>";
    }).join("");
  }
  scale("fitness-scale", data.fitness_bands);
  scale("workrate-scale", data.workrate_bands);

  document.getElementById("band-scale").innerHTML = data.bands.slice().reverse().map(function (b) {
    return '<div class="scale-row"><span class="pill ' + b.key + '">' + b.label +
           '</span><span class="val">' + fmt(b.value) + "</span></div>";
  }).join("");

  document.getElementById("vet-scale").innerHTML = data.vets.map(function (v) {
    return '<div class="scale-row"><span>' + v.label + '</span><span class="val">\u00d7' +
           v.modifier.toFixed(2) + "</span></div>";
  }).join("");

  function render() {
    const rows = data.rows.slice().sort(function (a, b) {
      const x = a[sortKey], y = b[sortKey];
      let cmp;
      if (typeof x === "string") { cmp = x.localeCompare(y); }
      else { cmp = x - y; }
      if (cmp === 0) { cmp = a.name.localeCompare(b.name); return cmp; }
      return sortDown ? -cmp : cmp;
    });

    document.getElementById("body").innerHTML = rows.map(function (r, i) {
      const tags =
        (r.captain ? '<span class="tag captain">C</span>' : "") +
        (r.keeper ? '<span class="tag keeper">GK</span>' : "");
      const maths = r.pinned
        ? "Set by hand at <b>" + fmt(r.rating) + "</b>. His bands alone would make him <b>" +
          fmt(r.derived) + "</b>."
        : r.band_label + " ability <b>" + fmt(r.band_value) + "</b>, " +
          r.fitness_label.toLowerCase() + " fitness <b>" + fmt(r.fitness_value) + "</b>, " +
          r.workrate_label.toLowerCase() + " workrate <b>" + fmt(r.workrate_value) + "</b>" +
          (r.captain ? ", plus <b>" + data.captain_self + "</b> for organising" : "") +
          (r.vet_modifier < 1 ? ", scaled <b>\u00d7" + r.vet_modifier.toFixed(2) + "</b> for " +
            r.vet_label.toLowerCase() : "") +
          ", so he rates <b>" + fmt(r.rating) + "</b>.";
      return (
        '<tr class="player" data-row="' + i + '" tabindex="0" role="button" aria-expanded="false">' +
          '<td><span class="who"><span class="name">' + r.name + "</span>" + tags + "</span></td>" +
          '<td><span class="pos">' + r.position + "</span></td>" +
          '<td><span class="pill ' + r.band + '">' + r.band_label + "</span></td>" +
          '<td><span class="pill ' + r.fitness + '">' + r.fitness_label + "</span></td>" +
          '<td><span class="pill ' + r.workrate + '">' + r.workrate_label + "</span></td>" +
          '<td class="vet-cell">' + (r.vet_label || "&mdash;") + "</td>" +
          '<td class="num"><span class="rating">' + fmt(r.rating) + "</span></td>" +
        "</tr>" +
        '<tr class="detail" hidden data-detail="' + i + '"><td colspan="7">' +
          '<p class="profile">' + (r.profile || "No profile written yet.") + "</p>" +
          '<p class="maths">' + maths + "</p>" +
        "</td></tr>"
      );
    }).join("");

    document.querySelectorAll("thead th button").forEach(function (btn) {
      const on = btn.dataset.sort === sortKey;
      btn.parentElement.toggleAttribute("aria-sort", on);
      if (on) { btn.parentElement.setAttribute("aria-sort", sortDown ? "descending" : "ascending"); }
      btn.querySelector(".arrow").textContent = sortDown ? "\\u25bc" : "\\u25b2";
    });
  }

  document.querySelectorAll("thead th button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const key = btn.dataset.sort;
      if (key === sortKey) { sortDown = !sortDown; }
      else { sortKey = key; sortDown = key !== "name" && key !== "position"; }
      render();
    });
  });

  function toggle(tr) {
    const detail = document.querySelector('[data-detail="' + tr.dataset.row + '"]');
    const open = !detail.hidden;
    detail.hidden = open;
    tr.classList.toggle("open", !open);
    tr.setAttribute("aria-expanded", String(!open));
  }

  document.getElementById("body").addEventListener("click", function (event) {
    const tr = event.target.closest("tr.player");
    if (tr) { toggle(tr); }
  });

  document.getElementById("body").addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") { return; }
    const tr = event.target.closest("tr.player");
    if (tr) { event.preventDefault(); toggle(tr); }
  });

  render();
</script>
"""
