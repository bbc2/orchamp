(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: bundled and served as a classic <script>, not an ES module
  "use strict";

  const SCORE_MIN = 0;
  const SCORE_MAX = 20;

  function intInRange(n) {
    return Number.isInteger(n) && n >= SCORE_MIN && n <= SCORE_MAX;
  }

  // Validate a score (string from a URL param, or number from localStorage
  // JSON) into an integer, or null. Strings must be plain digits (e.g. "5x" is
  // rejected, not silently truncated).
  function scoreFrom(v) {
    if (typeof v === "number") {
      return intInRange(v) ? v : null;
    }
    if (typeof v === "string" && /^\d+$/.test(v)) {
      const n = Number(v);
      return intInRange(n) ? n : null;
    }
    return null;
  }

  // Validate a raw [homeId, awayId, homeScore, awayScore] tuple from any
  // source (URL or localStorage) and return a normalized entry, or null.
  function normalizeEntry(e) {
    if (!Array.isArray(e) || e.length !== 4) return null;
    const homeId = e[0];
    const awayId = e[1];
    if (typeof homeId !== "string" || typeof awayId !== "string") return null;
    if (homeId.indexOf(":") !== -1 || awayId.indexOf(":") !== -1) return null;
    const homeScore = scoreFrom(e[2]);
    const awayScore = scoreFrom(e[3]);
    if (homeScore === null || awayScore === null) return null;
    return [homeId, awayId, homeScore, awayScore];
  }

  function parseParam(s) {
    return normalizeEntry(s.split(":"));
  }

  function serializeParam(entry) {
    return `${entry[0]}:${entry[1]}:${entry[2]}:${entry[3]}`;
  }

  function matchKey(homeId, awayId) {
    return `${homeId}:${awayId}`;
  }

  class AssumptionStore {
    constructor(leagueKey) {
      this._leagueKey = leagueKey;
      this._lsKey = `orchamp:assumptions:${leagueKey}`;
      this._map = new Map();
    }

    load() {
      const params = new URLSearchParams(window.location.search);
      const urlAssumptions = params.getAll("a");
      if (urlAssumptions.length > 0) {
        this._map.clear();
        for (const raw of urlAssumptions) {
          const entry = parseParam(raw);
          if (entry) {
            this._map.set(matchKey(entry[0], entry[1]), entry);
          }
        }
        this._persist();
      } else {
        try {
          const stored = localStorage.getItem(this._lsKey);
          if (stored) {
            const arr = JSON.parse(stored);
            this._map.clear();
            if (Array.isArray(arr)) {
              for (const raw of arr) {
                const e = normalizeEntry(raw);
                if (e) {
                  this._map.set(matchKey(e[0], e[1]), e);
                }
              }
            }
          }
        } catch (_) {}
      }
    }

    add(homeId, awayId, homeScore, awayScore) {
      this._map.set(matchKey(homeId, awayId), [
        homeId,
        awayId,
        homeScore,
        awayScore,
      ]);
      this._persist();
    }

    remove(homeId, awayId) {
      this._map.delete(matchKey(homeId, awayId));
      this._persist();
    }

    get(homeId, awayId) {
      return this._map.get(matchKey(homeId, awayId));
    }

    entries() {
      return Array.from(this._map.values());
    }

    toQueryString() {
      return this.entries()
        .map((e) => `a=${encodeURIComponent(serializeParam(e))}`)
        .join("&");
    }

    pruneStale(validKeys) {
      let changed = false;
      this._map.forEach((_, key) => {
        if (!validKeys.has(key)) {
          this._map.delete(key);
          changed = true;
        }
      });
      if (changed) this._persist();
    }

    _persist() {
      try {
        localStorage.setItem(this._lsKey, JSON.stringify(this.entries()));
      } catch (_) {}
      const qs = this.toQueryString();
      const newUrl = qs
        ? `${window.location.pathname}?${qs}`
        : window.location.pathname;
      history.replaceState(null, "", newUrl);
    }
  }

  function updateTeamLinks(store) {
    const entries = store.entries();
    document.querySelectorAll("a.team-link").forEach((link) => {
      const url = new URL(link.href);
      url.searchParams.delete("a");
      entries.forEach((e) => {
        url.searchParams.append("a", serializeParam(e));
      });
      link.href = url.toString();
    });
  }

  function updateRefreshButton(store) {
    const btn = document.querySelector(".refresh-btn[data-base-url]");
    if (!btn) return;
    const qs = store.toQueryString();
    btn.setAttribute("hx-get", btn.dataset.baseUrl + (qs ? `?${qs}` : ""));
  }

  function updateDynamicUrls(store) {
    updateTeamLinks(store);
    updateRefreshButton(store);
  }

  function refreshAssumptionsPanel(leagueKey, store) {
    const qs = store.toQueryString();
    const panelUrl = `/web/${leagueKey}/assumptions-panel${qs ? `?${qs}` : ""}`;
    htmx.ajax("GET", panelUrl, {
      target: "#assumptions-panel",
      swap: "innerHTML",
    });
    const tableUrl = `/web/${leagueKey}/standings-table${qs ? `?${qs}` : ""}`;
    htmx.ajax("GET", tableUrl, {
      target: "#standings-table",
      swap: "innerHTML",
    });
  }

  function removeAssumption(homeId, awayId) {
    const store = window._orchampStore;
    if (!store) return;
    store.remove(homeId, awayId);
    const row = document.querySelector(
      `tr.match-pending[data-home-id="${CSS.escape(homeId)}"][data-away-id="${CSS.escape(awayId)}"]`,
    );
    if (row) {
      row.querySelectorAll("input.score-input").forEach((input) => {
        input.value = "";
      });
    }
    updateDynamicUrls(store);
    refreshAssumptionsPanel(window._orchampLeagueKey, store);
  }

  // Delegated so it survives the htmx swaps that re-render the panel, and
  // avoids inline onclick (CSP-blocked, plus an id-escaping hazard).
  document.addEventListener("click", (event) => {
    const btn = event.target.closest?.(".remove-btn[data-home-id]");
    if (btn) {
      removeAssumption(btn.dataset.homeId, btn.dataset.awayId);
    }
  });

  window.orchampInitStandingsPage = (leagueKey, validMatchKeys) => {
    const store = new AssumptionStore(leagueKey);
    store.load();
    store.pruneStale(new Set(validMatchKeys));
    window._orchampStore = store;
    window._orchampLeagueKey = leagueKey;

    const timers = {};
    function debounce(key, fn, delay) {
      clearTimeout(timers[key]);
      timers[key] = setTimeout(fn, delay);
    }

    // Prefill each pending match's inputs from stored assumptions and wire up
    // change handling in a single pass over the rows.
    document
      .querySelectorAll("tr.match-pending[data-home-id]")
      .forEach((row) => {
        const homeId = row.dataset.homeId;
        const awayId = row.dataset.awayId;
        const homeInput = row.querySelector(
          'input.score-input[data-role="home"]',
        );
        const awayInput = row.querySelector(
          'input.score-input[data-role="away"]',
        );

        const entry = store.get(homeId, awayId);
        if (entry) {
          if (homeInput) homeInput.value = entry[2];
          if (awayInput) awayInput.value = entry[3];
        }

        function onChange() {
          const hVal = homeInput ? homeInput.value.trim() : "";
          const aVal = awayInput ? awayInput.value.trim() : "";
          if (hVal !== "" && aVal !== "") {
            const h = scoreFrom(hVal);
            const a = scoreFrom(aVal);
            if (h !== null && a !== null) {
              store.add(homeId, awayId, h, a);
            }
          } else if (hVal === "" && aVal === "") {
            store.remove(homeId, awayId);
          }
          debounce(
            "panel",
            () => {
              updateDynamicUrls(store);
              refreshAssumptionsPanel(leagueKey, store);
            },
            400,
          );
        }

        if (homeInput) homeInput.addEventListener("input", onChange);
        if (awayInput) awayInput.addEventListener("input", onChange);
      });

    updateDynamicUrls(store);

    // The table loads its own base content (server-rendered, or hx-trigger="load"
    // when lazy); refetch here only to project assumptions on top of it.
    if (store.entries().length > 0) {
      refreshAssumptionsPanel(leagueKey, store);
    }
  };
})();
