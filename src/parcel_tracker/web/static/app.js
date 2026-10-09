// parcel-tracker-bot dashboard: progressive enhancement only — every page works without it.
(function () {
  "use strict";
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem("ptb-theme");
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (e) { /* storage unavailable */ }

  function lang() { return root.getAttribute("lang") || undefined; }

  function localizeTimes() {
    var dtf = new Intl.DateTimeFormat(lang(), { dateStyle: "medium", timeStyle: "short" });
    var df = new Intl.DateTimeFormat(lang(), { dateStyle: "medium" });
    var md = new Intl.DateTimeFormat(lang(), { month: "short", day: "numeric" });
    var rtf = typeof Intl.RelativeTimeFormat === "function" ? new Intl.RelativeTimeFormat(lang(), { numeric: "auto" }) : null;
    document.querySelectorAll("time[datetime]").forEach(function (el) {
      var d = new Date(el.getAttribute("datetime"));
      if (isNaN(d)) return;
      var mode = el.getAttribute("data-format") || "datetime";
      el.title = dtf.format(d);
      if (mode === "date") { el.textContent = df.format(d); return; }
      if (mode === "relative" && rtf) {
        var secs = (d.getTime() - Date.now()) / 1000, abs = Math.abs(secs);
        var units = [["day", 86400], ["hour", 3600], ["minute", 60]];
        for (var i = 0; i < units.length; i++) {
          if (abs >= units[i][1] || units[i][0] === "minute") {
            el.textContent = rtf.format(Math.round(secs / units[i][1]), units[i][0]);
            return;
          }
        }
      }
      el.textContent = dtf.format(d);
    });
    document.querySelectorAll("text[data-date]").forEach(function (el) {
      var d = new Date(el.getAttribute("data-date") + "T00:00:00");
      if (!isNaN(d)) el.textContent = md.format(d);
    });
  }

  function tooltips() {
    var tip = null;
    function show(target, x, y) {
      if (!tip) { tip = document.createElement("div"); tip.className = "tooltip"; tip.setAttribute("role", "status"); document.body.appendChild(tip); }
      tip.textContent = target.getAttribute("data-tip");
      var w = tip.offsetWidth;
      tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x - w / 2)) + "px";
      tip.style.top = Math.max(8, y - tip.offsetHeight - 12) + "px";
      tip.hidden = false;
    }
    function hide() { if (tip) tip.hidden = true; }
    document.querySelectorAll("[data-tip]").forEach(function (el) {
      el.addEventListener("mousemove", function (ev) { show(el, ev.clientX, ev.clientY); });
      el.addEventListener("mouseleave", hide);
      el.addEventListener("focus", function () { var r = el.getBoundingClientRect(); show(el, r.left + r.width / 2, r.top + 24); });
      el.addEventListener("blur", hide);
    });
  }

  function copyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        var done = function () { var old = btn.textContent; btn.textContent = btn.getAttribute("data-copied") || "✓"; setTimeout(function () { btn.textContent = old; }, 1500); };
        if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
      });
    });
  }

  function confirmations() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        if (!window.confirm(form.getAttribute("data-confirm"))) ev.preventDefault();
      });
    });
  }

  function themeToggle() {
    var btn = document.querySelector("[data-theme-toggle]");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var dark = root.getAttribute("data-theme") === "dark" ||
        (!root.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
      var next = dark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("ptb-theme", next); } catch (e) { /* ignore */ }
    });
  }

  function autoSubmit() {
    document.querySelectorAll("select[data-autosubmit]").forEach(function (sel) {
      sel.addEventListener("change", function () { sel.form.submit(); });
    });
  }

  function hideBrokenMaps() {
    document.querySelectorAll("img[data-optional]").forEach(function (img) {
      var drop = function () { var box = img.closest("[data-map]"); if (box) box.hidden = true; };
      if (img.complete && img.naturalWidth === 0) drop();
      img.addEventListener("error", drop);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    localizeTimes(); tooltips(); copyButtons(); confirmations(); themeToggle(); autoSubmit(); hideBrokenMaps();
  });
})();
