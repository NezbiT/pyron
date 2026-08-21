(function () {
  var root = document.documentElement;
  var prefix = root.getAttribute("data-admin-prefix") || "/admin";
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function resolveSystem() {
    return media.matches ? "dark" : "light";
  }

  function applyTheme(choice) {
    if (choice === "system") {
      root.setAttribute("data-theme", resolveSystem());
      root.setAttribute("data-theme-source", "system");
    } else {
      root.setAttribute("data-theme", choice);
      root.setAttribute("data-theme-source", "user");
    }
  }

  function mark(group, value) {
    radios(group).forEach(function (btn, i) {
      var on = btn.getAttribute("data-value") === value;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
      if (on) group.style.setProperty("--i", String(i));
    });
  }

  function persist(params) {
    return fetch(prefix + "/prefs?" + params.toString(), {
      credentials: "same-origin",
      headers: { "X-Pyron-Prefs": "1", Accept: "text/plain" },
    });
  }

  function radios(group) {
    return Array.prototype.slice.call(group.querySelectorAll("[role=radio]"));
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-pref]");
    if (!btn) return;
    e.preventDefault();
    var kind = btn.getAttribute("data-pref");
    var value = btn.getAttribute("data-value");
    var group = btn.closest("[role=radiogroup]");
    if (btn.getAttribute("aria-checked") === "true") return;

    if (kind === "theme") {
      applyTheme(value);
      mark(group, value);
      persist(new URLSearchParams({ theme: value }));
      return;
    }
    if (kind === "lang") {
      mark(group, value);
      group.setAttribute("aria-busy", "true");
      persist(new URLSearchParams({ lang: value }))
        .then(function () {
          window.location.reload();
        })
        .catch(function () {
          btn.form && btn.form.submit();
        });
    }
  });

  document.addEventListener("keydown", function (e) {
    var keys = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };
    var btn = e.target.closest("button[data-pref]");
    if (!btn) return;
    var group = btn.closest("[role=radiogroup]");
    var items = radios(group);
    var i = items.indexOf(btn);
    if (e.key === "Home") {
      e.preventDefault();
      items[0].focus();
      return;
    }
    if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1].focus();
      return;
    }
    var delta = keys[e.key];
    if (!delta) return;
    e.preventDefault();
    var next = items[(i + delta + items.length) % items.length];
    next.focus();
    if (next.getAttribute("data-pref") === "theme") next.click();
  });

  try {
    media.addEventListener("change", function () {
      if (root.getAttribute("data-theme-source") === "system") {
        applyTheme("system");
      }
    });
  } catch (err) {}

  var ta = document.querySelector("[data-md-preview]");
  var out = document.querySelector("[data-md-output]");
  if (ta && out) {
    var csrf = document.querySelector('input[name="csrf"]');
    var timer = 0;
    function paint(html) {
      out.innerHTML = html || "";
    }
    function preview() {
      var body = new FormData();
      if (csrf) body.append("csrf", csrf.value);
      body.append("body", ta.value);
      fetch(prefix + "/preview-markdown", {
        method: "POST",
        body: body,
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.text();
        })
        .then(paint)
        .catch(function () {});
    }
    ta.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(preview, 280);
    });
  }

  var titleEl = document.getElementById("title");
  var slugEl = document.getElementById("slug");
  if (titleEl && slugEl && ta) {
    var slugTouched = slugEl.value.length > 0;
    slugEl.addEventListener("input", function () {
      slugTouched = true;
    });
    titleEl.addEventListener("input", function () {
      if (slugTouched) return;
      var raw = (titleEl.value || "").toLowerCase().trim();
      slugEl.value = raw.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
    });
  }
})();
