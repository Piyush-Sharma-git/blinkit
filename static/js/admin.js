/* =====================================================================
   admin.js - small helpers for the internal dashboard.
   Nothing here is trusted for business logic: the server recalculates
   totals and re-validates everything. JavaScript only improves usability.
   ===================================================================== */

const PALETTE = ["#0f5f4a", "#ff7a45", "#3a86c8", "#e0b02a", "#8b5fbf", "#2aa198",
                 "#d1495b", "#6c8a3c", "#c77d2e", "#5b6c8f", "#a3a3a3"];
const rupee = (v) => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });

function chartsAvailable(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (typeof Chart === "undefined") {        // static/js/chart.umd.min.js missing
    el.parentElement.innerHTML = '<p class="hint">Chart library not found: check static/js/chart.umd.min.js.</p>';
    return null;
  }
  return el;
}

function lineChart(id, labels, values, label) {
  const el = chartsAvailable(id);
  if (!el) return;
  new Chart(el, {
    type: "line",
    data: { labels, datasets: [{ label, data: values, borderColor: PALETTE[0],
            backgroundColor: "rgba(15,95,74,.12)", fill: true, tension: .3, pointRadius: 2 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
               tooltip: { callbacks: { label: (c) => rupee(c.parsed.y) } } },
               scales: { y: { ticks: { callback: rupee } } } }
  });
}

function barChart(id, labels, values, label) {
  const el = chartsAvailable(id);
  if (!el) return;
  new Chart(el, {
    type: "bar",
    data: { labels, datasets: [{ label, data: values, backgroundColor: PALETTE[0], borderRadius: 6 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
               tooltip: { callbacks: { label: (c) => rupee(c.parsed.y) } } },
               scales: { y: { ticks: { callback: rupee } } } }
  });
}

function doughnutChart(id, labels, values) {
  const el = chartsAvailable(id);
  if (!el) return;
  new Chart(el, {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 1 }] },
    options: { maintainAspectRatio: false, cutout: "58%",
               plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } },
                          tooltip: { callbacks: { label: (c) => c.label + ": " + rupee(c.parsed) } } } }
  });
}

/* ---------- confirm before destructive actions ----------
   Any <form data-confirm="message"> asks first. */
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});

/* ---------- New transaction form: add/remove rows + live estimate ---------- */
(function orderForm() {
  const table = document.getElementById("itemsBody");
  if (!table) return;
  const template = document.getElementById("rowTemplate");
  const estimate = document.getElementById("estimate");

  function recalc() {
    let total = 0;
    table.querySelectorAll("tr").forEach((row) => {
      const select = row.querySelector("select");
      const qtyInput = row.querySelector("input");
      const opt = select.selectedOptions[0];
      const price = opt ? parseFloat(opt.dataset.price || 0) : 0;
      const stock = opt ? parseInt(opt.dataset.stock || 0, 10) : 0;
      const qty = parseInt(qtyInput.value || 0, 10);
      const line = price * qty;
      row.querySelector(".line-total").textContent = price ? "₹" + line.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "-";
      row.querySelector(".stock-note").textContent = opt && opt.value ? `${stock} in stock` : "";
      row.querySelector(".stock-note").style.color = qty > stock ? "#c0392b" : "";
      total += line;
    });
    estimate.textContent = "₹" + total.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  document.getElementById("addRow").addEventListener("click", () => {
    table.appendChild(template.content.cloneNode(true));
    recalc();
  });
  table.addEventListener("click", (e) => {
    if (e.target.classList.contains("remove-row")) {
      if (table.querySelectorAll("tr").length > 1) e.target.closest("tr").remove();
      else { e.target.closest("tr").querySelector("select").value = ""; }
      recalc();
    }
  });
  table.addEventListener("input", recalc);
  table.addEventListener("change", recalc);
  recalc();
})();
