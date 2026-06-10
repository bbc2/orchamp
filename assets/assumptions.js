(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: bundled and served as a classic <script>, not an ES module
  "use strict";

  const SCORE_MIN = 0;
  const SCORE_MAX = 20;

  function intInRange(n) {
    return Number.isInteger(n) && n >= SCORE_MIN && n <= SCORE_MAX;
  }

  // Validate a score (string from a URL param or an input, or number from
  // localStorage JSON) into an integer, or null. Strings must be plain digits
  // (e.g. "5x" is rejected).
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

    // Drop entries whose match is no longer pending; returns whether anything
    // was dropped (so the caller knows a refetch is needed).
    pruneStale(validKeys) {
      let changed = false;
      this._map.forEach((_, key) => {
        if (!validKeys.has(key)) {
          this._map.delete(key);
          changed = true;
        }
      });
      if (changed) this._persist();
      return changed;
    }

    _persist() {
      try {
        localStorage.setItem(this._lsKey, JSON.stringify(this.entries()));
      } catch (_) {}
      const qs = this.toQueryString();
      const newUrl = qs
        ? `${window.location.pathname}?${qs}`
        : window.location.pathname;
      // Best-effort like localStorage: Safari throttles replaceState and
      // throws when typing fast; the next persist catches the URL up.
      try {
        history.replaceState(null, "", newUrl);
      } catch (_) {}
    }
  }

  // htmx owns all standings-table fetching (the lazy load, the refresh button,
  // the score-input trigger on the schedule table). Decorating the request
  // here means every fetch carries the same canonical ?a= state at the moment
  // it is issued, whichever element triggered it.
  document.body.addEventListener("htmx:configRequest", (event) => {
    const store = window._orchampStore;
    if (!store) return;
    if (!event.detail.path.endsWith("/standings-table")) return;
    for (const entry of store.entries()) {
      event.detail.parameters.append("a", serializeParam(entry));
    }
  });

  // Ask the schedule table to refetch the standings table (whose response also
  // carries the assumptions panel out-of-band).
  function refreshProjection() {
    const table = document.querySelector("table.schedule-table");
    if (table) htmx.trigger(table, "refresh-projection");
  }

  // Mirror a row's two inputs into the store: a complete valid pair is an
  // assumption; anything else (half-filled, out-of-range, junk the browser
  // reports as "") is none. The inputs are the source of truth, the store only
  // reflects them.
  function syncRow(row) {
    const store = window._orchampStore;
    if (!store) return;
    const homeInput = row.querySelector('input.score-input[data-role="home"]');
    const awayInput = row.querySelector('input.score-input[data-role="away"]');
    const home = homeInput ? scoreFrom(homeInput.value.trim()) : null;
    const away = awayInput ? scoreFrom(awayInput.value.trim()) : null;
    if (home !== null && away !== null) {
      store.add(row.dataset.homeId, row.dataset.awayId, home, away);
    } else {
      store.remove(row.dataset.homeId, row.dataset.awayId);
    }
  }

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!target.classList?.contains("score-input")) return;
    const row = target.closest("tr.match-pending[data-home-id]");
    if (row) syncRow(row);
  });

  // Delegated so it survives the htmx swaps that re-render the panel, and
  // avoids inline onclick (CSP-blocked, plus an id-escaping hazard).
  document.addEventListener("click", (event) => {
    const btn = event.target.closest?.(".remove-btn[data-home-id]");
    if (!btn) return;
    const store = window._orchampStore;
    if (!store) return;
    store.remove(btn.dataset.homeId, btn.dataset.awayId);
    const row = document.querySelector(
      `tr.match-pending[data-home-id="${CSS.escape(btn.dataset.homeId)}"][data-away-id="${CSS.escape(btn.dataset.awayId)}"]`,
    );
    if (row) {
      row.querySelectorAll("input.score-input").forEach((input) => {
        input.value = "";
      });
    }
    refreshProjection();
  });

  // Phase 1, synchronous at page load, before htmx fires any
  // hx-trigger="load" request: the store must already exist so configRequest
  // can decorate the lazy standings-table fetch with the assumptions.
  window.orchampInitAssumptions = (leagueKey) => {
    const store = new AssumptionStore(leagueKey);
    store.load();
    window._orchampStore = store;
  };

  // Phase 2, once the pending-match rows exist (immediately when eager, after
  // the lazy swap otherwise): prefill the inputs from the store and refetch
  // the table if it was rendered without the assumptions it should show.
  window.orchampInitSchedule = (validMatchKeys, tableAlreadyProjected) => {
    const store = window._orchampStore;
    const pruned = store.pruneStale(new Set(validMatchKeys));
    document
      .querySelectorAll("tr.match-pending[data-home-id]")
      .forEach((row) => {
        const entry = store.get(row.dataset.homeId, row.dataset.awayId);
        if (!entry) return;
        const homeInput = row.querySelector(
          'input.score-input[data-role="home"]',
        );
        const awayInput = row.querySelector(
          'input.score-input[data-role="away"]',
        );
        if (homeInput) homeInput.value = entry[2];
        if (awayInput) awayInput.value = entry[3];
      });
    if ((!tableAlreadyProjected && store.entries().length > 0) || pruned) {
      refreshProjection();
    }
  };
})();
