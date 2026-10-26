/* The water under the Roussillon: interactions and charts. No library: plain SVG.
   Data: window.EXPLAINER from data.js (made by src/analysis/explainer_data.py). */
(function () {
  "use strict";
  const D = window.EXPLAINER;
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function el(tag, attrs, parent, style) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    for (const k in style || {}) e.style[k] = style[k];
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, s, cls, attrs, style) {
    const t = el("text", Object.assign({ x: x, y: y, class: cls || "" }, attrs || {}), parent, style);
    t.textContent = s;
    return t;
  }
  function h(tag, attrs, html) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  const fmt = (v, d) => v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const LAYER_NAME = { alluvium: "river gravel layer", pliocene: "deep sand-and-clay layers",
    karst: "limestone with holes (karst)", other: "other rock" };
  const LAYER_VAR = { alluvium: "var(--alluvium)", pliocene: "var(--pliocene)",
    karst: "var(--karst)", other: "var(--other)" };

  /* ---------------------------------------------------------------- tooltip */
  const tip = $("#tip");
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.classList.add("on");
    const r = tip.getBoundingClientRect();
    let x = evt.clientX + 14, y = evt.clientY + 14;
    if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - 14;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function tipAt(node, html) { // keyboard focus: place next to the element
    const b = node.getBoundingClientRect();
    showTip({ clientX: b.right, clientY: b.top }, html);
  }
  const hideTip = () => tip.classList.remove("on");

  /* ---------------------------------------------------------------- theme */
  const themeBtn = $("#theme");
  const modes = ["auto", "light", "dark"];
  function applyTheme(m) {
    if (m === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", m);
    themeBtn.textContent = "Theme: " + m;
  }
  let theme = "auto";
  try { theme = localStorage.getItem("explainer-theme") || "auto"; } catch (e) { /* private mode */ }
  applyTheme(theme);
  themeBtn.addEventListener("click", () => {
    theme = modes[(modes.indexOf(theme) + 1) % modes.length];
    applyTheme(theme);
    try { localStorage.setItem("explainer-theme", theme); } catch (e) { /* ignore */ }
  });

  /* ---------------------------------------------------------------- rail */
  const sections = $$("main section");
  const toc = $("#toc"), sel = $("#toc-select");
  sections.forEach((s, i) => {
    const li = h("li");
    li.appendChild(h("a", { href: "#" + s.id },
      `${i + 1}. ${s.dataset.title}<span class="depth">${s.dataset.depth} down</span>`));
    toc.appendChild(li);
    const o = h("option", { value: s.id }, `${i + 1}. ${s.dataset.title}`);
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => { location.hash = sel.value; });
  const links = $$("#toc a"), items = $$("#toc li");
  function markCurrent(id) {
    const i = sections.findIndex(s => s.id === id);
    links.forEach((a, j) => a.setAttribute("aria-current", j === i ? "true" : "false"));
    items.forEach((li, j) => li.classList.toggle("passed", j <= i));
    sel.value = id;
    const last = items[i];
    if (last) $("#waterfill").style.height = (last.offsetTop + 14) + "px";
  }
  const io = new IntersectionObserver(entries => {
    const vis = entries.filter(e => e.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (vis.length) markCurrent(vis[0].target.id);
  }, { rootMargin: "-20% 0px -65% 0px" });
  sections.forEach(s => io.observe(s));
  markCurrent(sections[0].id);

  /* ---------------------------------------------------------------- hero */
  const INFO = {
    rain: ["Rain", "Rain falls mostly on the hills. Part of it soaks into the ground and slowly refills the underground layers. Experts call this refilling recharge."],
    hills: ["The hills", "The Corbières hills in the north and the Pyrenees mountains to the south-west. Their rain feeds the rivers and, through the rock, the layers under the plain."],
    river: ["A river, the Têt", "Rivers like the Têt and the Agly cross the plain. Near them, the shallow underground water and the river swap water all the time: they behave like one connected system."],
    canal: ["An irrigation canal", "Old canals carry river water to the fields. Some of it leaks into the ground and refills the shallow layer. That is the project's side story."],
    vines: ["Vineyards and orchards", "Vines cover about a third of the farmland near our wells. Most farm water (84 of every 100 litres) comes from rivers and canals; the rest is pumped from wells."],
    town: ["Perpignan and the villages", "Almost all their tap water (99 of every 100 litres) is pumped from underground, mostly from the deep layers. Towns and farms competing for that water is the project's main story."],
    sea: ["The Mediterranean Sea", "The rivers end here. For coastal underground water in general, very low levels near the sea can let salty sea water creep in."],
    alluvium: ["The river gravel layer (alluvium)", "Sand and gravel left by the rivers, just under the surface. In our wells it is reached within about 25 m. It fills and empties quickly with rain, rivers and canal leaks."],
    pliocene: ["The deep sand-and-clay layers (Pliocene)", "A thick pile of sand sheets separated by clay, laid down 2 to 5 million years ago, reached from about 10 to 250 m deep in our wells. The clay keeps the water under pressure. It is the main store of drinking water, and it reacts slowly."],
    karst: ["Limestone with holes (karst)", "Rock dissolved by water into cracks and tunnels, like Swiss cheese. Water can rush through quickly. Here it is the Corbières karst, partly hidden under the deep layers in the north."],
    rock: ["Older hard rock", "Below and around everything: old rock with little room for water. We do not model it."],
    level: ["The water level", "The height where the water stands in a well, in metres above sea level. It goes up in wet winters and down in dry summers and in droughts. This is what the computer must guess every week."],
    piezo: ["Measuring wells (twins)", "Thin pipes with a sensor that record the water level, often every day. Nobody pumps from them. Sometimes two stand side by side, one shallow and one deep, like the twins of Millas (chapter 3)."],
    tapwell: ["A drinking-water well", "It pumps water for the taps of the towns, mostly from the deep layers. Pumping lowers the water level around it, like drinking through a straw."],
    farmwell: ["A farm well", "One of about 1,900 underground pumping points in the plain; most are small farm wells. Each declares how much it pumped per year, not per week."]
  };
  const hots = $$(".hot");
  function pick(g) {
    const d = INFO[g.dataset.id];
    if (!d) return;
    hots.forEach(x => x.classList.toggle("on", x === g));
    $("#info-title").textContent = d[0];
    $("#info-text").textContent = d[1];
  }
  hots.forEach(g => {
    g.addEventListener("click", () => pick(g));
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(g); } });
  });

  /* ---------------------------------------------------------------- glossary */
  const WORDS = [
    ["aquifer", "Aquifer (water layer)", "A layer of sand, gravel or rock whose tiny gaps are full of water, like a soaked sponge. Wells pump from it.", "French: nappe, aquifère"],
    ["groundwater", "Groundwater", "Water stored underground in the gaps of sand, gravel and rock. It is not an underground lake."],
    ["level", "Water level", "The height where the water stands in a well, counted in metres above sea level. Higher means more water stored.", "Experts: hydraulic head; French: niveau piézométrique (m NGF)"],
    ["piezometer", "Measuring well", "A thin pipe down to one water layer, with a sensor that records the water level. Nobody pumps from it.", "Experts: piezometer; French: piézomètre"],
    ["core", "Core wells", "The 33 measuring wells with long, recent and regular records. Every result is reported on them."],
    ["pumping", "Pumping", "Taking water out of the ground (or a river) with a well or an intake.", "Experts: abstraction; French: prélèvement"],
    ["alluvium", "River gravel layer", "Sand and gravel left by rivers, close to the surface. It fills and empties fast.", "Experts: alluvium, alluvial aquifer; BD LISA codes 718BP…, 671AB…"],
    ["pliocene", "Deep sand-and-clay layers", "Many sheets of sand separated by clay, 2 to 5 million years old, reached from about 10 to 250 m deep in our wells. The main store of drinking water.", "Experts: the Pliocene multilayer aquifer; BD LISA code 671AA00"],
    ["karst", "Karst", "Limestone dissolved into cracks and tunnels. Water moves fast and in surprising ways.", "Here: the Corbières karst, BD LISA 681AM00"],
    ["recharge", "Recharge", "Water soaking down into an underground layer and refilling it, mostly from rain."],
    ["drought", "Drought", "A long dry period. In the Roussillon, 2022–2025 brought record-low water levels and water-use limits."],
    ["artesian", "Artesian", "When deep water is under so much pressure that it rises above the ground and flows out of the well by itself."],
    ["confined", "Confined layer", "A water layer sealed by clay above it. Its water is under pressure, like in a squeezed bottle."],
    ["irrigation", "Irrigation", "Watering crops. In the Roussillon mostly with river and canal water."],
    ["drinkingwater", "Drinking water", "Tap water. In the Roussillon almost all of it is pumped from underground.", "French: AEP (alimentation en eau potable)"],
    ["canal", "Canal", "An old channel taking water from a river to the fields. Its leaks refill the shallow layer."],
    ["stack", "Layer stack", "The list of layers you would cross if you drilled straight down at one spot, from the top down."],
    ["evaporation", "Evaporation", "Water the sun, heat and wind can take from soil and plants. High in summer.", "In the data: ETP (potential evapotranspiration)"],
    ["dataset", "Dataset (data version)", "The big table the computer learns from. There are four versions, v1 to v4, each fixing problems of the last."],
    ["model", "Model", "A computer recipe that turns inputs (weather, pumping) into an answer (the water level). Training means letting it learn the recipe from past examples."],
    ["training", "Study years (training)", "2005–2019. The computer studies them with the answers."],
    ["validation", "Practice exam (validation)", "January 2020 to April 2022. Used to choose settings, never as the final exam."],
    ["test", "Final exam (test)", "May 2022 to now, never looked at while building. Scored in two parts: the drought (May 2022 – November 2025) and the recovery (December 2025 – now)."],
    ["simulation", "Simulation", "Guessing the level from weather and pumping only, without ever seeing a real level. The project's main task."],
    ["forecast", "Forecast", "Guessing the level a few weeks ahead when you know today's level. Easier, and a different game."],
    ["hindcast", "Hindcast", "A forecast made after the fact, with some inputs that were not known at the time (here the yearly pumping totals). Our forecast task is really one."],
    ["baseline", "Rival (baseline)", "A model that ours must beat. Without rivals, a score means nothing."],
    ["climatology", "Normal-year guess", "\"This week the level will be as it usually is at this time of year.\" The simplest rival.", "Experts: climatology"],
    ["pastas", "Pastas", "The hydrologists' standard tool. Each cause (rain, evaporation, pumping) leaves a footprint on the level over the following weeks; the footprints are added up."],
    ["lightgbm", "LightGBM", "Many small yes/no question trees (\"is it summer?\", \"did it rain a lot?\") that vote together."],
    ["lstm", "LSTM and EA-LSTM", "Neural networks with a memory that read the last years of weather week by week. In the EA-LSTM, each well's fixed facts (depth, place) steer what it remembers."],
    ["gnn", "Graph network", "A neural network where each well passes messages to the wells it is linked to, like neighbours talking. The links can come from distance or from the knowledge map.", "Experts: (spatio-temporal) graph neural network, ST-GNN"],
    ["chronos", "Chronos-2", "A large forecasting model trained on huge numbers of time series. It looks at past levels, so it plays the forecast game, where it is the champion."],
    ["ensemble", "Team of models", "The average of several models: their mistakes partly cancel.", "Experts: ensemble"],
    ["tuning", "Tuning", "Trying many settings (size, memory length, learning speed) and keeping the best on the practice exam. Every rival got the same 24 tries."],
    ["seed", "Random start", "A neural network starts from random numbers. Each one is trained 5 times from different random starts and averaged, so luck matters less.", "Experts: seed"],
    ["skill", "Skill", "How much smaller the mistakes are than those of the normal-year guess: 0 = no better, 0.5 = about half the mistakes (in squared size), 1 = perfect."],
    ["nse", "NSE", "A common hydrology score. 1 = perfect, 0 = no better than a flat line at the average of the scored period, below 0 = worse than that.", "Nash–Sutcliffe efficiency"],
    ["significance", "Proven difference", "A test of whether a difference could just be luck. \"Proven\" usually means less than a 5 % chance of luck.", "Experts: statistical significance, p-value"],
    ["cluster", "Neighbourhood", "A 10 km square of the map. Wells in the same square behave alike, so the fair test counts them together. The 33 core wells sit in 14 squares.", "Experts: spatial cluster"],
    ["effectsize", "Size of the difference", "How big an improvement is, for example \"half the mistakes\". Reported first, before saying whether it is proven.", "Experts: effect size"],
    ["hiddenwells", "Hidden-well test", "Some wells are hidden while the computer studies, then it must guess them. Repeated 5 times with different groups. It tests wells that are monitored but left out, not places with no well at all.", "Experts: leave-wells-out cross-validation"],
    ["fold", "Group of hidden wells", "One of the 5 groups of the hidden-well test. From v4, wells closer than 2 km always share a group.", "Experts: fold"],
    ["quality", "Quality labels", "Each measurement is labelled by its operator: \"Correcte\" (checked, fine), \"Non qualifié\" (not checked yet), \"Incorrecte\" (checked, wrong). Version 4 removes the wrong ones."],
    ["placeholder", "Placeholder value", "A number written into a record when nothing was really measured, such as a depth of exactly 0.00 m every day for months. It looks valid and can even be labelled \"Correcte\", so only a written rule catches it."],
    ["reconstructed", "Reconstruction", "Values filled in by reasoned guessing when the real numbers do not exist: weekly pumping (only yearly totals are declared), pumping before 2012, or 2025–2026 (not published yet).", "Experts: imputed data"],
    ["sgi", "Drought class", "A level turned into \"how unusual for this month at this well\", from \"very low\" to \"very high\", like the official drought bulletins.", "Experts: SGI (Standardised Groundwater Index), BRGM IPS classes"],
    ["ontology", "Knowledge map", "A dictionary of the things in our world (well, layer, pump) and of how they can be linked (pumps from, lies on), written so that a computer can read and check it. The facts written with it form the knowledge graph.", "Experts: ontology, knowledge graph (KG)"],
    ["cq", "Competency questions", "The questions the knowledge map must answer, such as \"which pumps take water from the same layer as this well?\". They are its checklist and its tests."],
    ["reuse", "Reuse", "Borrowing words from international vocabularies instead of inventing our own, so that other projects can connect to ours."],
    ["confidence", "Confidence", "How sure we are of a fact: confident (an official record), probable (a clue measured to be right at least 8 times in 10), possible (a weaker or unmeasured clue), unknown."],
    ["constraint", "Rule", "Something the model must respect, such as \"more pumping can never raise the level\".", "Experts: constraint"],
    ["monotone", "Built-in rule", "The model is built so that it cannot break the rule at all, whatever it learns.", "Experts: monotone by construction"],
    ["shortcut", "Shortcut", "Getting the right answer for the wrong reason, like a student who memorises answers without understanding. We test for it.", "Experts: reasoning shortcut"],
    ["twin", "Practice world", "Fake water levels made with our real weather and pumps but with rules we choose, so the right answer is known and we can check whether the model finds it.", "Experts: semi-synthetic twin"],
    ["rewiring", "Scrambled map", "The links of the knowledge map are shuffled. If the model does just as well with nonsense links, it was not really using them.", "Experts: rewiring, semantic ablation"],
    ["hybrid", "Hybrid model", "Our main model: each kind of cause gets its own footprint with a fixed direction, shaped by the knowledge map, plus a small free part."],
    ["arms", "Arms", "The versions of the model that are compared (A to F); each adds or removes one ingredient."],
    ["faithful", "Faithful explanation", "An explanation that really describes how the model computed its answer, not a nice story added afterwards.", "Experts: faithfulness, fidelity"],
    ["review", "Review", "A strict check of the work by someone else, to find mistakes before a journal does."],
    ["leak", "Data leak", "When information from the final exam sneaks into the studying. It makes results look better than they are."],
    ["gate", "Gate", "A checkpoint with the supervisor before moving to the next phase."],
    ["hubeau", "Hub'Eau", "Free French public services (APIs) for water data: levels, river flows, pumping, water quality."],
    ["bnpe", "BNPE", "The national register of declared water pumping: how much each pumping point took each year."],
    ["bdlisa", "BD LISA", "The national map of France's underground layers, with a code for each layer."],
    ["rpg", "RPG", "The register of farm fields and crops that farmers declare each year for EU subsidies."],
    ["safran", "SAFRAN", "Météo-France's daily weather for all of France on 8 km squares: rain, temperature, evaporation, soil wetness."],
    ["bss", "BSS code", "The national ID number of every borehole in France."],
    ["kc", "Crop coefficient", "How much water a crop uses compared with a short lawn, through its season: low after planting, highest in mid-season. Its water need is about this number times the weather's evaporation.", "Experts: Kc (FAO-56)"],
    ["thirst", "Crop thirst", "The water the crops around a well would need beyond the rain that fell, week by week. It says what crops would need, not what was really pumped.", "Experts: potential irrigation demand"],
    ["registration", "Registration effect", "A change in the crop maps that comes from what farmers declare (a new code, land declared for the first time), not from a change in the fields."]
  ];
  const WORD = {};
  WORDS.forEach(w => { WORD[w[0]] = w; });

  let openTerm = null;
  const pop = h("div", { class: "pop", role: "dialog", hidden: "" });
  document.body.appendChild(pop);
  function closePop() {
    pop.hidden = true;
    if (openTerm) openTerm.setAttribute("aria-expanded", "false");
    openTerm = null;
  }
  $$(".term").forEach(b => {
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", e => {
      e.stopPropagation();
      if (openTerm === b) { closePop(); return; }
      closePop();
      const w = WORD[b.dataset.term];
      if (!w) return;
      pop.innerHTML = `<b>${w[1]}</b>${w[2]}${w[3] ? `<span class="fr">${w[3]}</span>` : ""}`;
      pop.hidden = false;
      const r = b.getBoundingClientRect();
      const left = Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - pop.offsetWidth - 12);
      pop.style.left = Math.max(8, left) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
      b.setAttribute("aria-expanded", "true");
      openTerm = b;
    });
  });
  document.addEventListener("click", e => { if (!pop.contains(e.target)) closePop(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { closePop(); hideTip(); } });

  const list = $("#word-list");
  WORDS.slice().sort((a, b) => a[1].localeCompare(b[1])).forEach(w => {
    const d = h("div", { "data-s": (w[1] + " " + w[2] + " " + (w[3] || "")).toLowerCase() });
    d.appendChild(h("dt", {}, w[1]));
    d.appendChild(h("dd", {}, w[2] + (w[3] ? `<br><span class="note">${w[3]}</span>` : "")));
    list.appendChild(d);
  });
  $("#word-search").addEventListener("input", e => {
    const q = e.target.value.trim().toLowerCase();
    $$("#word-list > div").forEach(d => { d.hidden = q && !d.dataset.s.includes(q); });
  });

  /* ---------------------------------------------------------------- helpers for charts */
  function niceTicks(lo, hi, n) {
    const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  const DAY = 86400000;
  const t0 = Date.parse(D.series.start + "T00:00:00Z");
  const weekDate = i => new Date(t0 + i * 7 * DAY);
  const dateTxt = d => d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const idxOf = iso => Math.round((Date.parse(iso + "T00:00:00Z") - t0) / (7 * DAY));

  /* line chart with period bands; series = [{name, values, color, dash?, optional?}];
     an optional series is left out of the tooltip where it has no value */
  function lineChart(host, series, opts) {
    host.innerHTML = "";
    const W = 760, H = 334, m = { l: 52, r: 16, t: 42, b: 34 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label, tabindex: "0" }, host);
    const n = D.series.n;
    const vals = series.flatMap(s => s.values).filter(v => v !== null);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = Math.max(0.05 * (hi - lo), 0.2);
    lo -= pad; hi += pad;
    const x = i => m.l + (W - m.l - m.r) * i / (n - 1);
    const y = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
    const bands = [["train", "study years", "var(--band-train)"], ["validation", "practice", "var(--band-val)"],
      ["drought", "drought", "var(--band-drought)"], ["recovery", "recovery", "var(--band-recovery)"]];
    bands.forEach(([k, lab, fill]) => {
      const p = D.periods[k];
      const a = Math.max(0, idxOf(p[0])), b = p[1] ? Math.min(n - 1, idxOf(p[1])) : n - 1;
      el("rect", { x: x(a), y: m.t, width: Math.max(1, x(b) - x(a)), height: H - m.t - m.b }, svg, { fill: fill });
      text(svg, x(a) + 3, m.t - 8, lab, "band-label");
    });
    const g = el("g", { class: "grid" }, svg);
    niceTicks(lo, hi, 5).forEach(v => {
      el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, g);
      text(svg, m.l - 6, y(v) + 4, fmt(v, Math.abs(hi - lo) < 8 ? 1 : 0), "tick", { "text-anchor": "end" }, { fill: "var(--muted)", font: "400 11.5px var(--sans)" });
    });
    const ax = el("g", { class: "axis" }, svg);
    el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }, ax);
    for (let yr = 2005; yr <= 2026; yr += 3) {
      const i = idxOf(yr + "-01-01");
      if (i < 0 || i >= n) continue;
      text(ax, x(i), H - m.b + 16, String(yr), "", { "text-anchor": "middle" });
    }
    text(svg, 4, 13, "Water level, metres above sea level", "band-label");
    series.forEach(s => {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v === null) { pen = false; return; }
        d += (pen ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1);
        pen = true;
      });
      el("path", Object.assign({ d: d, fill: "none", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" },
        s.dash ? { "stroke-dasharray": s.dash } : {}), svg, { stroke: s.color });
    });
    // hover layer
    const cross = el("line", { y1: m.t, y2: H - m.b, "stroke-width": 1 }, svg, { stroke: "var(--ink-2)", opacity: 0 });
    const dots = series.map(s => el("circle", { r: 4.5, "stroke-width": 2 }, svg, { fill: s.color, stroke: "var(--paper)", opacity: 0 }));
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    let cur = n - 1;
    function show(i, evt) {
      cur = Math.max(0, Math.min(n - 1, i));
      cross.setAttribute("x1", x(cur)); cross.setAttribute("x2", x(cur)); cross.style.opacity = 1;
      let html = `<b>Week of ${dateTxt(weekDate(cur))}</b>`;
      series.forEach((s, k) => {
        const v = s.values[cur];
        if (v === null) { dots[k].style.opacity = 0; if (!s.optional) html += `<br>${s.name}: no measurement`; return; }
        dots[k].setAttribute("cx", x(cur)); dots[k].setAttribute("cy", y(v)); dots[k].style.opacity = 1;
        html += `<br>${s.name}: ${fmt(v, 2)} m`;
      });
      if (evt) showTip(evt, html); else tipAt(dots.find(d => d.style.opacity === "1") || svg, html);
    }
    function clear() { cross.style.opacity = 0; dots.forEach(d => { d.style.opacity = 0; }); hideTip(); }
    hit.addEventListener("mousemove", e => {
      const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
      const q = p.matrixTransform(svg.getScreenCTM().inverse());
      show(Math.round((q.x - m.l) / (W - m.l - m.r) * (n - 1)), e);
    });
    hit.addEventListener("mouseleave", clear);
    svg.addEventListener("keydown", e => {
      if (e.key === "ArrowLeft") { e.preventDefault(); show(cur - 4); }
      if (e.key === "ArrowRight") { e.preventDefault(); show(cur + 4); }
    });
    svg.addEventListener("blur", clear);
  }

  /* ---------------------------------------------------------------- water level chart */
  const wellBy = {};
  D.wells.forEach(w => { wellBy[w.code] = w; });
  const EX = [["10908X0263/FIGUER", "Perpignan, deep"], ["10971X0155/PD5", "Corneilla, deep"],
    ["10972X0003/ALENYA", "Alénya, river gravel"], ["10903X0034/PZSTGL", "Estagel, karst"],
    ["10906X0039/C2-1", "Millas, shallow"], ["10906X0038/C2-2", "Millas, deep"]];
  const levelBox = $("#level-wells");
  function drawLevel(code) {
    const w = wellBy[code], masked = (D.series.masked || {})[code];
    const lines = [{ name: w.name, values: D.series.values[code], color: LAYER_VAR[w.layer] }];
    if (masked) lines.push({ name: "left out of the scores", values: masked, color: "var(--critical)", dash: "5 4", optional: true });
    lineChart($("#chart-level"), lines,
      { label: `Weekly water level of ${w.name}, ${w.town}, 2005 to now` + (masked ? ", with the weeks left out of the scores dashed" : "") });
    $("#level-legend").innerHTML = `<span><i class="key line" style="background:${LAYER_VAR[w.layer]}"></i>${w.name} (${w.town}): ${LAYER_NAME[w.layer]}, ${w.depth} m deep</span>` +
      (masked ? `<span><i class="key line" style="background:repeating-linear-gradient(90deg, var(--critical) 0 5px, transparent 5px 9px)"></i>dashed: not a measurement (depth exactly 0.00 m), left out of the scores</span>` : "");
    $$("button", levelBox).forEach(b => b.setAttribute("aria-pressed", String(b.dataset.code === code)));
  }
  EX.forEach(([code, lab]) => {
    const b = h("button", { class: "btn", type: "button", "data-code": code, "aria-pressed": "false" }, lab);
    b.addEventListener("click", () => drawLevel(code));
    levelBox.appendChild(b);
  });
  const about = h("table");
  about.innerHTML = "<tr><th>Well</th><th>Town</th><th>Layer</th><th class='num'>Depth (m)</th></tr>" +
    EX.map(([c]) => { const w = wellBy[c]; return `<tr><td>${w.name}</td><td>${w.town}</td><td>${LAYER_NAME[w.layer]}</td><td class="num">${w.depth}</td></tr>`; }).join("");
  $("#level-about").appendChild(about);
  drawLevel(EX[0][0]);

  /* twins of Millas */
  lineChart($("#chart-twins"), [
    { name: "shallow well (9 m)", values: D.series.values["10906X0039/C2-1"], color: "var(--alluvium)" },
    { name: "deep well (109 m)", values: D.series.values["10906X0038/C2-2"], color: "var(--pliocene)" }],
    { label: "Weekly levels of the two Millas wells, 20 m apart, one shallow and one deep" });
  $("#twins-legend").innerHTML =
    `<span><i class="key line" style="background:var(--alluvium)"></i>shallow well, 9 m, in the river gravel</span>` +
    `<span><i class="key line" style="background:var(--pliocene)"></i>deep well, 109 m, in the deep layers</span>`;

  /* ---------------------------------------------------------------- map */
  const PERPIGNAN = [2.8956, 42.6986];
  const PLAIN = [2.55, 42.50, 3.06, 42.88];
  function sites(pairs) { // group twin pairs into sites (connected wells)
    const parent = {};
    const find = a => (parent[a] === a ? a : (parent[a] = find(parent[a])));
    pairs.forEach(p => { parent[p.a] = parent[p.a] || p.a; parent[p.b] = parent[p.b] || p.b; });
    pairs.forEach(p => { parent[find(p.a)] = find(p.b); });
    const groups = {};
    pairs.forEach(p => {
      const r = find(p.a);
      groups[r] = groups[r] || { wells: new Set(), pairs: [] };
      groups[r].wells.add(p.a); groups[r].wells.add(p.b); groups[r].pairs.push(p);
    });
    return Object.values(groups);
  }
  const SITES = sites(D.twins);
  function drawMap(mode) {
    const host = $("#chart-map");
    host.innerHTML = "";
    // frame: the core wells and the plain (the few extra wells up in the hills are counted below)
    const core = D.wells.filter(w => w.core);
    const lons = core.map(w => w.lon).concat([PLAIN[0], PLAIN[2]]);
    const lats = core.map(w => w.lat).concat([PLAIN[1], PLAIN[3]]);
    const lo0 = Math.min(...lons) - 0.04, lo1 = Math.max(...lons) + 0.13;
    const la0 = Math.min(...lats) - 0.04, la1 = Math.max(...lats) + 0.04;
    const inFrame = w => w.lon >= lo0 && w.lon <= lo1 && w.lat >= la0 && w.lat <= la1;
    const outside = D.wells.filter(w => !inFrame(w)).length;
    const k = Math.cos((la0 + la1) / 2 * Math.PI / 180);
    const W = 760, pad = 20, sx = (W - 2 * pad) / ((lo1 - lo0) * k);
    const H = Math.round((la1 - la0) * sx + 2 * pad);
    const X = lon => pad + (lon - lo0) * k * sx, Y = lat => pad + (la1 - lat) * sx;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": mode === "layers" ? "Map of the 65 measuring wells coloured by layer" : `Map of the twin wells in dataset ${mode}` }, host);
    el("rect", { x: X(PLAIN[0]), y: Y(PLAIN[3]), width: X(PLAIN[2]) - X(PLAIN[0]), height: Y(PLAIN[1]) - Y(PLAIN[3]), rx: 10 }, svg,
      { fill: "var(--tint)" });
    text(svg, X(PLAIN[0]) + 8, Y(PLAIN[3]) + 18, "the plain", "band-label");
    const halo = { stroke: "var(--paper)", strokeWidth: "4px", paintOrder: "stroke", strokeLinejoin: "round" };
    const showWell = (w, evt) => {
      const html = `<b>${w.name}</b><br>${w.town}<br>${LAYER_NAME[w.layer]}${w.depth ? `, ${w.depth} m deep` : ""}<br>${w.core ? "core well" : "extra well (training only)"}` +
        (mode !== "layers" ? `<br>hidden-well group in ${mode}: ${mode === "v3" ? w.fold3 + 1 : w.fold4 + 1}` : "");
      if (evt) showTip(evt, html); else tipAt(evt || svg, html);
    };
    const order = D.wells.filter(inFrame).sort((a, b) => a.core - b.core);
    order.forEach(w => {
      const color = mode === "layers" ? LAYER_VAR[w.layer] : "var(--other)";
      el("circle", { cx: X(w.lon), cy: Y(w.lat), r: w.core ? 6 : 3.6, "stroke-width": 2 }, svg,
        { fill: color, stroke: "var(--paper)", opacity: mode === "layers" ? 1 : 0.7 });
      const hit = el("circle", { cx: X(w.lon), cy: Y(w.lat), r: 10, fill: "transparent", tabindex: "0", "aria-label": `${w.name}, ${w.town}` }, svg);
      hit.addEventListener("mousemove", e => showWell(w, e));
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("focus", () => tipAt(hit, `<b>${w.name}</b><br>${w.town}<br>${LAYER_NAME[w.layer]}`));
      hit.addEventListener("blur", hideTip);
    });
    if (mode !== "layers") {
      SITES.forEach(s => {
        const ws = Array.from(s.wells).map(c => wellBy[c]);
        if (!ws.every(inFrame)) return;
        const cx = ws.reduce((a, w) => a + X(w.lon), 0) / ws.length;
        const cy = ws.reduce((a, w) => a + Y(w.lat), 0) / ws.length;
        const split = s.pairs.some(p => (mode === "v3" ? p.split3 : p.split4));
        el("circle", { cx: cx, cy: cy, r: 13, fill: "none", "stroke-width": 2.5 }, svg,
          { stroke: split ? "var(--critical)" : "var(--good)" });
        text(svg, cx + 15, cy + 4, split ? "✕" : "✓", "value-label", {}, { fill: split ? "var(--critical)" : "var(--good)" });
      });
    }
    // labels last, with a halo, so they stay readable over the dots
    el("rect", { x: X(PERPIGNAN[0]) - 4, y: Y(PERPIGNAN[1]) - 4, width: 8, height: 8 }, svg, { fill: "var(--ink)" });
    text(svg, X(PERPIGNAN[0]) - 8, Y(PERPIGNAN[1]) + 20, "Perpignan", "value-label", { "text-anchor": "end" }, halo);
    text(svg, X(3.08), Y(42.68), "sea", "band-label", {}, halo);
    text(svg, X(3.08), Y(42.68) + 15, "this way", "band-label", {}, halo);
    if (outside) text(svg, 12, H - 10, `${outside} extra wells up in the hills are off this map`, "band-label", {}, halo);
    const leg = $("#map-legend");
    if (mode === "layers") {
      leg.innerHTML = ["alluvium", "pliocene", "karst", "other"].map(l =>
        `<span><i class="key dot" style="background:${LAYER_VAR[l]}"></i>${LAYER_NAME[l]} (${D.wells.filter(w => w.layer === l && w.core).length} core)</span>`).join("");
    } else {
      const nSplit = D.twins.filter(p => (mode === "v3" ? p.split3 : p.split4)).length;
      leg.innerHTML = `<span><i class="key dot" style="border:2.5px solid var(--critical);background:none"></i>✕ twins split between groups</span>` +
        `<span><i class="key dot" style="border:2.5px solid var(--good);background:none"></i>✓ twins hidden together</span>` +
        `<span>${nSplit} of ${D.twins.length} pairs closer than 1 km are split in ${mode}</span>`;
    }
  }
  $$("#map-modes button").forEach(b => b.addEventListener("click", () => {
    $$("#map-modes button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    drawMap(b.dataset.mode);
  }));
  drawMap("layers");

  /* ---------------------------------------------------------------- drops pictogram */
  function drops(host, title, nUnder, note) {
    const box = h("div", { class: "drops" });
    box.appendChild(h("h4", {}, title));
    const svg = el("svg", { viewBox: "0 0 210 210", role: "img",
      "aria-label": `${title}: ${nUnder} of every 100 litres from underground, ${100 - nUnder} from rivers and canals` }, box);
    const drop = "M0,-8 C4,-3 7,1 7,4.5 A7,7 0 1,1 -7,4.5 C-7,1 -4,-3 0,-8 z";
    for (let i = 0; i < 100; i++) {
      const r = Math.floor(i / 10), c = i % 10;
      el("path", { d: drop, transform: `translate(${12 + c * 20.5},${14 + r * 20})` }, svg,
        { fill: i < nUnder ? "var(--pliocene)" : "var(--alluvium)" });
    }
    box.appendChild(h("p", { class: "note" }, note));
    host.appendChild(box);
  }
  const dropsHost = $("#drops");
  drops(dropsHost, "Tap water", 99, "99 of every 100 litres are pumped from underground (475 of 478 million m³, 2012–2023).");
  drops(dropsHost, "Farm water", 16, "84 of every 100 litres come from rivers and canals (741 of 885 million m³, 2012–2023).");
  dropsHost.insertAdjacentHTML("beforeend",
    `<div class="legend" style="grid-column:1/-1"><span><i class="key" style="background:var(--pliocene)"></i>from underground</span>` +
    `<span><i class="key" style="background:var(--alluvium)"></i>from rivers and canals</span></div>`);

  /* ---------------------------------------------------------------- scores */
  function drawScores(period) {
    const host = $("#chart-scores");
    host.innerHTML = "";
    const rows = D.scores;
    const key = period === "drought" ? "skill_drought" : "skill_recovery";
    const W = 760, lab = 300, bh = 22, gap = 16, top = 10;
    const H = top + rows.length * (bh + gap) + 24;
    const lo = Math.min(0, ...rows.map(r => r[key])), hi = 1;
    const x = v => lab + (W - lab - 50) * (v - lo) / (hi - lo);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Skill of each rival in the ${period}` }, host);
    const g = el("g", { class: "grid" }, svg);
    [0, 0.25, 0.5, 0.75, 1].forEach(v => {
      el("line", { x1: x(v), x2: x(v), y1: top - 4, y2: H - 22 }, g);
      text(svg, x(v), H - 6, String(v), "tick", { "text-anchor": "middle" }, { fill: "var(--muted)", font: "400 11.5px var(--sans)" });
    });
    rows.forEach((r, i) => {
      const yy = top + i * (bh + gap);
      const v = r[key];
      text(svg, lab - 10, yy + bh / 2 + 4, r.label, "cat-label", { "text-anchor": "end" });
      const x0 = x(Math.min(0, v)), w = Math.max(2, Math.abs(x(v) - x(0)));
      const bar = el("rect", { x: x0, y: yy, width: w, height: bh, rx: 4 }, svg,
        { fill: r.kind === "ml" ? "var(--model)" : "var(--plain-bar)" });
      text(svg, x(Math.max(0, v)) + 6, yy + bh / 2 + 4, fmt(v, 2), "value-label");
      const hit = el("rect", { x: lab - 290, y: yy - 6, width: W - lab + 290, height: bh + 12, fill: "transparent", tabindex: "0",
        "aria-label": `${r.label}: skill ${fmt(v, 2)}` }, svg);
      const html = `<b>${r.label}</b><br>skill in the drought: ${fmt(r.skill_drought, 2)}<br>skill in the recovery: ${fmt(r.skill_recovery, 2)}<br>NSE in the drought: ${fmt(r.nse_drought, 2)}`;
      hit.addEventListener("mousemove", e => showTip(e, html));
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("focus", () => tipAt(bar, html));
      hit.addEventListener("blur", hideTip);
    });
    el("line", { x1: x(0), x2: x(0), y1: top - 4, y2: H - 22, "stroke-width": 1.5 }, svg, { stroke: "var(--ink-2)" });
    $$("#score-period button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.period === period)));
  }
  $$("#score-period button").forEach(b => b.addEventListener("click", () => drawScores(b.dataset.period)));
  drawScores("drought");
  $("#scores-legend").innerHTML = `<span><i class="key" style="background:var(--model)"></i>computer-learning models</span>` +
    `<span><i class="key" style="background:var(--plain-bar)"></i>simple guess and hydrology tools</span>`;
  $("#scores-table").innerHTML = "<table><tr><th>Rival</th><th class='num'>Skill, drought</th><th class='num'>Skill, recovery</th><th class='num'>NSE, drought</th></tr>" +
    D.scores.map(r => `<tr><td>${r.label}</td><td class="num">${fmt(r.skill_drought, 2)}</td><td class="num">${fmt(r.skill_recovery, 2)}</td><td class="num">${fmt(r.nse_drought, 2)}</td></tr>`).join("") + "</table>";

  /* ---------------------------------------------------------------- attribution */
  const CONF = [["confident", "confident: official record", "var(--c1)"], ["probable", "probable: clue right 9 times in 10 for this use", "var(--c2)"],
    ["possible", "possible: weaker or unmeasured clue", "var(--c3)"], ["unknown", "unknown", "var(--c4)"]];
  const USES = [["drinking water", "Drinking water"], ["irrigation", "Farm watering"], ["industry", "Industry"], ["canals", "Canals"]];
  (function drawAttrib() {
    const host = $("#chart-attrib");
    const by = D.attribution.by_use;
    const tot = u => CONF.reduce((a, c) => a + (by[u] ? by[u][c[0]] : 0), 0);
    const max = Math.max(...USES.map(u => tot(u[0])));
    const W = 760, lab = 150, bh = 24, gap = 22, top = 8;
    const H = top + USES.length * (bh + gap);
    const x = v => (W - lab - 120) * v / max;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Underground water pumped by use and by confidence about its layer" }, host);
    USES.forEach(([u, name], i) => {
      const yy = top + i * (bh + gap);
      text(svg, lab - 10, yy + bh / 2 + 4, name, "cat-label", { "text-anchor": "end" });
      let cx = lab;
      CONF.forEach(([c, cname, color]) => {
        const v = by[u] ? by[u][c] : 0;
        if (v <= 0) return;
        const w = Math.max(1, x(v) - 2);
        const seg = el("rect", { x: cx, y: yy, width: w, height: bh, rx: 3 }, svg, { fill: color });
        const html = `<b>${name}</b><br>${cname}<br>${fmt(v, 1)} million m³ (${Math.round(100 * v / tot(u))} %)`;
        seg.addEventListener("mousemove", e => showTip(e, html));
        seg.addEventListener("mouseleave", hideTip);
        cx += w + 2;
      });
      text(svg, cx + 6, yy + bh / 2 + 4, `${fmt(tot(u), 0)} million m³`, "value-label");
    });
  })();
  $("#attrib-legend").innerHTML = CONF.map(c => `<span><i class="key" style="background:${c[2]}"></i>${c[1]}</span>`).join("");
  $("#attrib-table").innerHTML = "<table><tr><th>Use</th>" + CONF.map(c => `<th class="num">${c[0]}</th>`).join("") + "</tr>" +
    USES.map(([u, name]) => `<tr><td>${name}</td>` + CONF.map(c => `<td class="num">${fmt(D.attribution.by_use[u] ? D.attribution.by_use[u][c[0]] : 0, 1)}</td>`).join("") + "</tr>").join("") +
    "</table><p class='note'>Million m³, declared years 2012–2024, plain only. Rules checked on " + D.attribution.n_recorded + " boreholes with a known layer.</p>";

  /* ---------------------------------------------------------------- versions */
  const V = D.versions;
  const VERSIONS = {
    v1: { title: "Version 1: the first draft", when: "13 October, Step 8",
      changes: [`${V.v1.wells} wells, all inside the plain (${V.v1.core} core)`, "Study years start in 2012, the first year of the pumping register",
        `Pumping points within the plain plus 3 km (${V.v1.pumps.toLocaleString("en-GB")})`, `Last real pumping year: ${V.v1.last_bnpe}`],
      why: "A first complete table, to run the first rivals and see what is hard." },
    v2: { title: "Version 2: more wells, a longer memory", when: "13 October, Step 10",
      changes: [`All ${V.v2.wells} usable wells of the département (the same ${V.v2.core} core wells); the extra wells only help the computer learn`,
        "Study years start in 2005, with weather from 2000 so that the models can warm up",
        "Pumping of the whole département; 2005–2011, before the register, filled in from the 2012–2014 average and marked as filled",
        `${V.v2.pumps.toLocaleString("en-GB")} pumping points`],
      why: "More wells and more years give the computer more examples to learn from. Two half-versions (v2a, v2b) checked which of the two changes helped." },
    v3: { title: "Version 3: cleaner pumping data", when: "20 October, Step 12a",
      changes: ["A new download of the register, with the real 2024 volumes",
        "Written rules for the register's problems: missing use labels, the 2018 jump in declarations, late declarations, years not published yet",
        "A leak fixed: the share of days when the water flows out by itself now uses study years only",
        "River flows added as inputs; only the plain's canals count",
        "Drought restriction orders kept for explanations, never used as inputs: they are triggered by the very levels we predict"],
      why: "The first check-up showed that pumping, the most important cause, was the weakest part of the data." },
    v4: { title: "Version 4: honest checks", when: "23 October, Step 12b",
      changes: [`${V.v4.dropped} measurements marked "incorrect" by their operators removed: 63 weeks disappear, 8 change slightly`,
        "Each week records whether all its measurements were checked",
        "In the hidden-well test, wells closer than 2 km are always hidden together",
        "The less-data test computes each well's averages from its own years only",
        "Added on 24 October: the scores leave out 60 weeks at Corneilla whose record is a placeholder (a depth of exactly 0.00 m for 413 days); the table itself keeps them",
        "Everything else is identical to version 3"],
      why: "The second check-up. Status: built and tested; the rivals are being re-run on it, on Kaggle and Colab, since 24 October." }
  };
  const tabs = $("#version-tabs");
  function showVersion(v) {
    const d = VERSIONS[v];
    $("#version-card").innerHTML = `<h3>${d.title}</h3><p class="sub">${d.when}</p><ul class="changes">${d.changes.map(c => `<li>${c}</li>`).join("")}</ul><p class="why"><strong>Why:</strong> ${d.why}</p>`;
    $$("button", tabs).forEach(b => b.setAttribute("aria-selected", String(b.dataset.v === v)));
    $$("button", tabs).forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
  }
  Object.keys(VERSIONS).forEach(v => {
    const b = h("button", { class: "btn", type: "button", role: "tab", "data-v": v }, v);
    b.addEventListener("click", () => showVersion(v));
    tabs.appendChild(b);
  });
  showVersion("v4");
  const rowsV = [
    ["Wells (core)", v => `${V[v].wells} (${V[v].core})`],
    ["Study years start", v => (v === "v1" ? "2012" : "2005")],
    ["Weekly rows with a level", v => V[v].weeks.toLocaleString("en-GB")],
    ["Pumping points", v => V[v].pumps.toLocaleString("en-GB")],
    ["Last real pumping year", v => String(V[v].last_bnpe)],
    ["Pumping data rules", v => (v === "v1" || v === "v2" ? "basic" : "written rules")],
    ["Bad measurements removed", v => String(V[v].dropped)],
    ["Placeholder weeks left out of the scores", v => (v === "v4" ? "60 (Corneilla)" : "none")],
    ["Hidden-well groups", v => (v === "v4" ? "close wells together" : "random")],
    ["Less-data test averages", v => (v === "v4" ? "own years only" : "all study years")]
  ];
  const vs = ["v1", "v2", "v3", "v4"];
  $("#version-table").innerHTML = "<table><tr><th></th>" + vs.map(v => `<th>${v}</th>`).join("") + "</tr>" +
    rowsV.map(([name, f]) => "<tr><td>" + name + "</td>" + vs.map((v, i) => {
      const val = f(v), changed = i > 0 && val !== f(vs[i - 1]);
      return `<td class="${changed ? "cell-new" : ""}">${val}</td>`;
    }).join("") + "</tr>").join("") + "</table><p class='note'>Shaded cells changed from the version before.</p>";

  /* ---------------------------------------------------------------- decisions */
  const DEC = [
    ["made", "Where?", "One place, done well: the Roussillon plain.", "Open data on everything and 35-year records. A Master's needs one system done end to end. A small demo in Tunisia (Manouba) only if its data arrive by February."],
    ["made", "How often?", "One value per week.", "The level changes slowly; weeks are enough and less noisy."],
    ["made", "What game?", "Simulation (no peeking at real levels), not forecasting; the title says \"simulation\".", "We want to understand causes. Chronos-2 already wins the forecasting game."],
    ["made", "Which story?", "Main story: tap-water pumping pressing on the deep layers, in a plain of farms (sharpened on 24 October). Side story: canal leaks refilling the river gravel.", "20 of the 33 core wells are in the deep layers, 99 % of tap water comes from underground, and a BRGM bulletin documented a rise in 2024 after pumping was reduced. No farm well has a sure enough layer, so farm pumping is tested only on the side, with all links, and marked provisional."],
    ["made", "The karst wells?", "Kept.", "The karst lies under the deep layers, so it belongs in the map. Results are always shown per layer."],
    ["made", "Which main model?", "The hybrid: footprints shaped by the knowledge map, with fixed directions, plus a small free part.", "Every link of the map gets a job, the rules hold by construction and the explanations are exact. A free black-box network is the comparison."],
    ["made", "How to enforce the rules?", "Built into the model, not checked afterwards (PiShield dropped).", "Our rules are about the direction of a response, which PiShield cannot express."],
    ["made", "How to catch cheating?", "Practice worlds with known answers, including harder ones; scrambled maps; agreement between repeats.", "The only tests that can catch a shortcut. The drought class is reported but is not the cheating test."],
    ["made", "Shallow always above deep?", "No such rule.", "In 17 nearby pairs the shallow water was higher only half of the time."],
    ["made", "Water-use limits as an input?", "Never.", "The limits are triggered by the very levels we predict: using them would be cheating."],
    ["made", "Fair contest?", "Same tuning budget for every rival (24 tries), 5 random starts each.", "Otherwise the best-tuned model wins, not the best idea."],
    ["made", "Fair statistics?", "Count neighbourhoods, not wells; report the size of each difference first.", "Neighbouring wells agree, so 33 wells are not 33 witnesses."],
    ["made", "Which data version?", "Dataset v4, with the rivals re-run on it using the settings found on v3.", "It removes wrong measurements and the twin-well shortcut."],
    ["made", "How to spread pumping over weeks?", "Test three ways; a conclusion must hold for all three.", "Weekly pumping is a reconstruction, not a measurement."],
    ["made", "When to fix the plan?", "Freeze the analysis plan with a git tag before Phase 4, then check on new weeks.", "So that results cannot steer the analysis."],
    ["made", "What does the knowledge map claim?", "Clarity, checking and reuse; better predictions are credited to the knowledge itself.", "The same facts in plain tables would give the same links."],
    ["made", "Where to publish?", "Environmental Modelling & Software first, then JGR: Machine Learning and Computation.", "It fits methods, software and ontologies, and it does not require a publication fee."],
    ["made", "Pump links in the main runs?", "Confident + probable links (24 October). Confident only, and all links, are side tests.", "They cover 72 % of the plain's declared underground pumping for the layer family (62 % for the exact layer), against 27 % for confident only. Pumping without a sure layer is never counted as zero."],
    ["made", "Re-run the rivals on v4?", "Yes, on Kaggle and Colab, never on the laptop (24 October).", "The laptop stays free, and Kaggle keeps running even when it is off."],
    ["made", "Which Pastas is the yardstick?", "From v4: the Pastas fit that only sees the levels of the study years, its start picked by a fixed rule, whatever its final-exam score (24 October, before its results).", "The usual set-up peeks at the whole series, final exam included, to set its starting level. Choosing after seeing the scores would look like picking the winner."],
    ["made", "C against D: what changes?", "Only the links: same model, inputs, budget and random starts for arms C to F, plus three controls fixed in advance (24 October).", "Otherwise a gain could come from the model, not from the meaning of the links."],
    ["made", "The flat line at Corneilla?", "Left out of every score by a written rule: 28 days or more at a depth of exactly 0.00 m (24 October). Scores are also shown without the rule.", "For 413 days the record says 0.00 m, labelled correct, while wells where water really flows out record negative depths. It is not a measurement."],
    ["made", "Back to the subject: crops", "Yearly crop maps 2015–2025 for the whole département; a weekly crop-thirst number per well (25 October).", "The subject is about land use and water, and no crop information was used yet (fourth check-up). The département, not only the plain, so the mountain wells are measured too."],
    ["made", "Which questions are core?", "Nine: the six of 24 October, plus crops and their water needs, satellite signs of irrigation, and explanations of real outputs (25 October).", "Finishing the core questions must mean the subject's whole chain is covered: land use, water, model, explanation."],
    ["made", "Does crop information help?", "A test written before any run: the same models with and without the crop thirst, plus a fake version with another well's crops (25 October).", "Only a fair comparison can show the model uses the crops; a no is reported as it is."],
    ["made", "Geography or change?", "A fourth version of the crop test: the 2019 crops frozen for every year (25 October, before any run).", "Beating the fake crops shows the model uses each well's own crops, but not whether it uses where they are or how they change. Only the real crops beating the frozen ones speaks about change."],
    ["made", "Which crops count in the crop thirst?", "The ones that are mostly watered: orchards, vegetables, artichokes, maize, citrus. Vines, olives and the like only in a side version (25 October, before any run).", "The 2020 farm census: only about 1 vine in 20 is irrigated, against most orchards and vegetables. Counting every vineyard would fill the number with water nobody uses."],
    ["made", "Which comparison counts in the crop test?", "With crops against without crops, both trained in the same Kaggle job (26 October, before any result was read).", "The run without crops from the first Colab session was trained on another kind of computer. That alone moved the LSTM's score by about as much as the effect we were testing."],
    ["wait", "The other questions of the knowledge map", "Nine are core (six approved on 24 October, three made core on 25 October); review the other 7: add, drop, set priorities.", "The design of the map is frozen after your review."],
    ["wait", "Two e-mails", "Send them: the decisions and the defence date to the supervisor; the request for monthly drinking-water data.", "The defence date sets the whole schedule; monthly data would separate pumping from weather."],
    ["wait", "A note about Corneilla", "Send it to the operator of the well (SMNPR); the French text is ready.", "Their answer decides whether the rule stays or a corrected record replaces the flat line."],
    ["wait", "Earth Engine account", "Later, for the satellite rule (task 12.10).", "The sign-in is yours."],
    ["wait", "Two paywalled papers", "Read the full texts of Chu et al. 2026 and Jeong et al. 2026 through the university (their summaries are read).", "Jeong already checks learned responses against independent estimates, so we cite that idea and do not claim it."]
  ];
  const decList = $("#decision-list");
  function showDec(f) {
    decList.innerHTML = DEC.filter(d => f === "all" || d[0] === f).map(d =>
      `<li><div class="q">${d[1]}${d[0] === "wait" ? '<span class="badge wait">waiting for you</span>' : ""}</div><div class="a">${d[2]}</div><p class="because">${d[3]}</p></li>`).join("");
    $$("#decision-filters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.f === f)));
  }
  $$("#decision-filters button").forEach(b => b.addEventListener("click", () => showDec(b.dataset.f)));
  showDec("all");

  /* ---------------------------------------------------------------- footer */
  $("#footer").innerHTML = `Charts drawn from the project's data on ${D.generated} (commit ${D.commit}). ` +
    `To refresh them: <code>.venv/bin/python -m src.analysis.explainer_data</code>, then reload this page. ` +
    `Open this guide any time from <code>docs/explainer/index.html</code>.`;
})();
