/*
  worldmap.js: the interactive world map (design: docs/design-worldmap.md).

  Two jobs, plain JavaScript, no framework:

  1. HOME MAP (home.html, section .world-map)
     The page already draws both islands and their spot buttons (so it works
     even without JavaScript). This script:
       - turns the island headings into tabs (only one island shows at a time)
       - fills the spot panel when you click a spot, using the spot data the
         server put in <script id="world-data"> (backend contract v2.6: world_maps)

  2. "SHOW ON MAP" PINGS (any page)
     Any element with data-locate="monster=ID" (or npc=ID / map=ID) opens the
     shared <dialog id="map-dialog"> from base.html. We ask the server
     GET /api/locate?monster=ID for the ping points, and GET /api/world/{world}
     for the island picture and its size, then draw pulsing pings.
     Without JavaScript the button is a plain link to /api/locate.

  Spot and ping coordinates are pixels on the original picture, so we place
  them in percent: left = x / width * 100%, top = y / height * 100%.
*/
(function () {
  "use strict";

  // Tell the CSS that JavaScript is running (hides the "no JS" island headings).
  document.documentElement.classList.add("wm-js");

  // ---------- small helpers ----------

  // Make an element: el("li", {class: "x"}, "text" or [children])
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] === null || attrs[k] === undefined || attrs[k] === false) return;
      node.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    [].concat(children === undefined ? [] : children).forEach(function (c) {
      if (c === null || c === undefined) return;
      node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return node;
  }

  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  // A monster or NPC picture; falls back to the leaf placeholder if missing.
  function sprite(kind, id) {
    var ext = kind === "monsters" ? "webp" : "png";
    var img = el("img", { src: "/static/img/" + kind + "/" + id + "." + ext, alt: "", loading: "lazy" });
    img.onerror = function () { img.onerror = null; img.src = "/static/img/placeholder.svg"; };
    return el("span", { class: "slot" }, img);
  }

  // Place something on the picture in percent of the picture's size.
  function placeAt(node, x, y, world) {
    node.style.left = (x / world.width * 100) + "%";
    node.style.top = (y / world.height * 100) + "%";
  }

  // Island tabs: click, or Left/Right arrow keys, to switch. onSelect(index) does the switching.
  function wireTabs(tablist, onSelect) {
    var tabs = [].slice.call(tablist.querySelectorAll('[role="tab"]'));
    function select(i, focus) {
      tabs.forEach(function (t, j) {
        t.setAttribute("aria-selected", j === i ? "true" : "false");
        t.tabIndex = j === i ? 0 : -1;     // only the selected tab is in the Tab order
      });
      if (focus) tabs[i].focus();
      onSelect(i);
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(i, false); });
      t.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") { e.preventDefault(); select((i + 1) % tabs.length, true); }
        if (e.key === "ArrowLeft") { e.preventDefault(); select((i - 1 + tabs.length) % tabs.length, true); }
      });
    });
    return select;
  }

  // =================================================================
  // 1. HOME MAP
  // =================================================================
  function initHomeMap() {
    var section = document.querySelector(".world-map");
    var dataTag = document.getElementById("world-data");
    if (!section || !dataTag) return;
    var worlds = JSON.parse(dataTag.textContent);   // [WorldMap, WorldMap]
    var islands = [].slice.call(section.querySelectorAll(".wm-island"));
    var tablist = section.querySelector(".wm-tabs");
    var panelTitle = section.querySelector("#wm-panel-title");
    var panelBody = section.querySelector(".wm-panel .win-body");

    // Tabs: show one island at a time. Victoria Island first (most of the game is there).
    var showIsland = function (i) {
      islands.forEach(function (isl, j) { isl.hidden = j !== i; });
    };
    tablist.hidden = false;
    var start = Math.max(0, islands.findIndex(function (isl) { return isl.dataset.world === "victoria-island"; }));
    wireTabs(tablist, showIsland)(start, false);

    // Clicking a spot fills the panel.
    section.addEventListener("click", function (e) {
      var btn = e.target.closest(".wm-spot");
      if (!btn) return;
      var world = worlds.find(function (w) { return w.world === btn.dataset.world; });
      // Find the spot by its position (the server groups maps so there is one spot per x,y).
      var spot = world && world.spots.find(function (s) { return String(s.x) === btn.dataset.x && String(s.y) === btn.dataset.y; });
      if (!spot) return;
      section.querySelectorAll('.wm-spot[aria-pressed="true"]').forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      btn.setAttribute("aria-pressed", "true");
      fillPanel(spot);
      // Phones: the panel is under the map, so bring it into view.
      if (window.matchMedia("(max-width: 860px)").matches) {
        var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        section.querySelector(".wm-panel").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      }
    });

    // One group in the panel: a heading and a list. Long lists show the first
    // `limit` items and a "Show all N" button for the rest.
    function addGroup(heading, list, limit) {
      var items = [].slice.call(list.children);
      items.forEach(function (li, i) { if (i >= limit) li.hidden = true; });
      var group = el("div", { class: "wm-group" }, [el("h3", {}, heading), list]);
      if (items.length > limit) {
        var more = el("button", { type: "button", class: "wm-more" }, "Show all " + items.length);
        more.addEventListener("click", function () {
          items.forEach(function (li) { li.hidden = false; });
          more.remove();
        });
        group.appendChild(more);
      }
      panelBody.appendChild(group);
    }

    function fillPanel(spot) {
      panelTitle.textContent = spot.label;
      panelBody.textContent = "";

      // Maps here (plain chips: we don't have map pages).
      if (spot.maps.length) {
        addGroup("Maps", el("ul", { class: "map-list" }, spot.maps.map(function (mp) {
          return el("li", { class: "pill pill-tag", title: mp.exact ? null : "Exact spot not known: shown at its town" },
                    mp.name + (mp.exact ? "" : " (approximate)"));
        })), 8);
      }

      // Monsters here, each linking to its page.
      if (spot.monsters.length) {
        addGroup("Monsters", el("ul", { class: "rows" }, spot.monsters.map(function (mo) {
          return el("li", {}, [
            sprite("monsters", mo.id),
            el("span", { class: "main" }, el("a", { href: "/monsters/" + mo.id }, mo.name)),
            mo.level ? el("span", { class: "end muted" }, "Lv " + mo.level) : null
          ]);
        })), 6);
      }

      // NPCs: shopkeepers under "Shops", everyone else under "NPCs".
      var shops = spot.npcs.filter(function (n) { return n.has_shop; });
      var others = spot.npcs.filter(function (n) { return !n.has_shop; });
      [["Shops", shops], ["NPCs", others]].forEach(function (pair) {
        if (!pair[1].length) return;
        addGroup(pair[0], el("ul", { class: "rows" }, pair[1].map(function (n) {
          return el("li", {}, [sprite("npcs", n.id), el("span", { class: "main" }, el("a", { href: "/npcs/" + n.id }, n.name))]);
        })), 6);
      });

      if (!spot.monsters.length && !spot.npcs.length) {
        panelBody.appendChild(el("p", { class: "wm-hint" }, "We don't have monsters or shops listed for this spot yet."));
      }
    }
  }

  // =================================================================
  // 2. "SHOW ON MAP" PING DIALOG
  // =================================================================
  var worldCache = {};   // world slug -> WorldMap (fetched once per page)

  function getWorld(slug) {
    if (!worldCache[slug]) {
      worldCache[slug] = fetch("/api/world/" + encodeURIComponent(slug)).then(function (r) {
        if (!r.ok) throw new Error("world " + r.status);
        return r.json();
      });
    }
    return worldCache[slug];
  }

  function initPingDialog() {
    var dialog = document.getElementById("map-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return;   // very old browser: links still work
    var title = dialog.querySelector("#map-dialog-title-text");
    var tablist = dialog.querySelector(".wm-tabs");
    var mapBox = dialog.querySelector(".wm-dialog-map");
    var status = dialog.querySelector(".wm-status");
    var list = dialog.querySelector(".wm-ping-list");
    var unplacedBox = dialog.querySelector(".wm-unplaced");
    var opener = null;      // the button that opened the dialog (focus goes back to it)
    var lastQuery = null;   // for "Try again"

    // Close: the X button, Esc (built into <dialog>), or a click on the dark backdrop.
    dialog.querySelector(".wm-close").addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function () {
      if (opener && document.body.contains(opener)) opener.focus();
    });

    // Every "Show on map" button on the page (event delegation, so HTMX-loaded ones work too).
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-locate]");
      if (!btn) return;
      e.preventDefault();   // stay on the page instead of following the /api/locate link
      opener = btn;
      open(btn.dataset.locate, btn.dataset.label || "");
    });

    function reset(label) {
      title.textContent = (label || "This place") + " on the map";
      tablist.hidden = true;
      tablist.textContent = "";
      mapBox.textContent = "";
      list.textContent = "";
      unplacedBox.textContent = "";
      unplacedBox.hidden = true;
    }

    function showError(label) {
      status.textContent = "Couldn't load the map. ";
      var retry = el("button", { type: "button", class: "wm-more" }, "Try again");
      retry.addEventListener("click", function () { open(lastQuery, label); });
      status.appendChild(retry);
    }

    function open(query, label) {
      lastQuery = query;
      reset(label);
      status.textContent = "Finding spots…";
      if (!dialog.open) dialog.showModal();

      fetch("/api/locate?" + query)
        .then(function (r) { if (!r.ok) throw new Error("locate " + r.status); return r.json(); })
        .then(function (loc) {
          if (!label) title.textContent = loc.name + " on the map";
          if (loc.unplaced && loc.unplaced.length) {
            unplacedBox.textContent = "Not on the map yet: " + loc.unplaced.join(", ");
            unplacedBox.hidden = false;
          }
          if (!loc.pings.length) {
            status.textContent = "We don't know where this is on the map yet.";
            return;
          }
          // Load every island that has pings, then draw.
          return Promise.all(loc.worlds.map(getWorld)).then(function (worlds) {
            status.textContent = "";
            draw(loc, worlds);
          });
        })
        .catch(function () { showError(label); });
    }

    function draw(loc, worlds) {
      // Pings grouped by island.
      var byWorld = worlds.map(function (w) {
        return { world: w, pings: loc.pings.filter(function (p) { return p.world === w.world; }) };
      });

      // Each island's picture + pings, built once; tabs switch between them.
      var panes = byWorld.map(function (g) {
        var canvas = el("div", { class: "wm-canvas" }, el("img", {
          src: g.world.image_url, alt: g.world.name + " world map", width: g.world.width, height: g.world.height
        }));
        // Every spot on the island as a plain map dot (like the home map), so the
        // lit-up pings below are easy to place among all the other locations.
        (g.world.spots || []).forEach(function (s) {
          var dot = el("span", { class: "wm-bg-dot" + (s.is_town ? " is-town" : ""), "aria-hidden": "true" });
          placeAt(dot, s.x, s.y, g.world);
          canvas.appendChild(dot);
        });
        g.pings.forEach(function (p) {
          var count = (p.map_names || []).length;
          var ping = el("span", { class: "wm-ping" + (p.exact ? "" : " approx") }, [
            el("span", { class: "ring" }), el("span", { class: "ring" }), el("span", { class: "dot" }),
            count > 1 ? el("span", { class: "badge", "aria-hidden": "true" }, count) : null
          ]);
          placeAt(ping, p.x, p.y, g.world);
          canvas.appendChild(ping);
        });
        return canvas;
      });

      // The text list under the map: the same places in words (the pings are never the only answer).
      function fillList(i) {
        list.textContent = "";
        byWorld[i].pings.forEach(function (p) {
          var names = p.map_names && p.map_names.length ? p.map_names : [p.map_name];
          names.forEach(function (name) {
            list.appendChild(el("li", {}, [name, p.exact ? null : el("span", { class: "approx" }, " (approximate: shown at the town)")]));
          });
        });
      }

      function show(i) {
        mapBox.textContent = "";
        mapBox.appendChild(panes[i]);
        fillList(i);
      }

      // Open on the island with the most pings.
      var best = 0;
      byWorld.forEach(function (g, i) { if (g.pings.length > byWorld[best].pings.length) best = i; });

      if (byWorld.length > 1) {
        byWorld.forEach(function (g) {
          tablist.appendChild(el("button", { type: "button", role: "tab" }, [g.world.name + " ", el("span", { class: "count" }, g.pings.length)]));
        });
        tablist.hidden = false;
        wireTabs(tablist, show)(best, false);
      } else {
        show(0);
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initHomeMap();
    initPingDialog();
  });
})();
