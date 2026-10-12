/*
  price-chart.js: draws the market price chart on item pages.

  It looks for <canvas id="price-chart" data-url="/api/items/123/price-history">,
  fetches that JSON (a list of {date, median, low, high, count}, oldest first),
  and draws:
    - a solid line for the daily median
    - a light shaded band between each day's low and high
  Needs Chart.js, which item.html loads from a CDN before this file.
*/
(function () {
  var canvas = document.getElementById("price-chart");
  if (!canvas || typeof Chart === "undefined") return;

  // If there's nothing to draw, swap the chart box for a short message.
  function showMessage(text) {
    var box = canvas.parentElement;
    var p = document.createElement("p");
    p.className = "muted";
    p.textContent = text;
    box.replaceWith(p);
  }

  // Read colors from our CSS variables (site.css) so the chart matches light and dark mode.
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  var lineColor = cssVar("--mw-chart", "#1D2846");
  var textColor = cssVar("--mw-muted", "#7D6A55");
  var gridColor = cssVar("--mw-wood-soft", "#D9C2A0");
  Chart.defaults.font.family = "Nunito, system-ui, sans-serif";

  // Use the line color at low opacity for the low/high band.
  function withAlpha(color, alpha) {
    // Handles "#rrggbb" and "rgb(...)"; anything else just falls back to grey.
    if (color[0] === "#" && color.length === 7) {
      var r = parseInt(color.slice(1, 3), 16),
          g = parseInt(color.slice(3, 5), 16),
          b = parseInt(color.slice(5, 7), 16);
      return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
    }
    if (color.indexOf("rgb(") === 0) {
      return color.replace("rgb(", "rgba(").replace(")", "," + alpha + ")");
    }
    return "rgba(128,128,128," + alpha + ")";
  }

  // 12500 -> "12,500"
  function fmt(n) {
    return n == null ? "—" : Number(n).toLocaleString();
  }

  fetch(canvas.dataset.url)
    .then(function (res) { return res.json(); })
    .then(function (days) {
      if (!days || days.length === 0) {
        // No daily history to draw (rare: the page only shows the chart when there are reports).
        showMessage("No price history to chart yet.");
        return;
      }

      var labels = days.map(function (d) { return d.date; });

      new Chart(canvas, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            // 1) Daily high: an invisible line that is the top edge of the band.
            {
              label: "High",
              data: days.map(function (d) { return d.high; }),
              borderWidth: 0,
              pointRadius: 0,
              pointHitRadius: 0,
              fill: "+1",                      // shade down to the next dataset (Low)
              backgroundColor: withAlpha(lineColor, 0.15)
            },
            // 2) Daily low: the bottom edge of the band.
            {
              label: "Low",
              data: days.map(function (d) { return d.low; }),
              borderWidth: 0,
              pointRadius: 0,
              pointHitRadius: 0,
              fill: false
            },
            // 3) Daily median: the main line.
            {
              label: "Median",
              data: days.map(function (d) { return d.median; }),
              borderColor: lineColor,
              backgroundColor: lineColor,
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 5,
              tension: 0.2,
              fill: false
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,          // fill the .chart-box height from CSS
          interaction: { mode: "index", intersect: false },  // hover anywhere on a day
          plugins: {
            legend: { display: false },        // the caption under the chart explains the band
            tooltip: {
              // One tooltip per day showing median, low-high range and number of reports.
              filter: function (item) { return item.dataset.label === "Median"; },
              callbacks: {
                label: function (ctx) {
                  var d = days[ctx.dataIndex];
                  return [
                    "Median: " + fmt(d.median) + " mesos",
                    "Range: " + fmt(d.low) + " – " + fmt(d.high),
                    d.count + " report" + (d.count === 1 ? "" : "s")
                  ];
                }
              }
            }
          },
          scales: {
            x: {
              ticks: { color: textColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
              grid: { display: false }
            },
            y: {
              beginAtZero: false,
              ticks: { color: textColor, callback: function (v) { return fmt(v); } },
              grid: { color: gridColor }
            }
          }
        }
      });
    })
    .catch(function () {
      showMessage("Couldn't load the price history. Reload the page to try again.");
    });
})();
