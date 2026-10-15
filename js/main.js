/* ==========================================================================
   main.js: loads each chart's Vega-Lite spec from /specs and draws it.

   How it works
   1. Every chart on the page is a <figure class="chart" data-spec="specs/xxx.vl.json" data-height="400">.
   2. When a figure scrolls near the screen, loadChart() fetches its spec and calls vegaEmbed().
   3. The chart is drawn at the width of its container, with the "..." actions menu turned off.
   4. If anything fails (file missing, bad JSON, library blocked) the labelled placeholder stays
      and shows a plain-English message saying what went wrong.

   Plain JavaScript, no framework. Libraries (vega, vega-lite, vega-embed) are loaded in index.html.
   ========================================================================== */

(function () {
  'use strict';

  /* ---------- Settings you may want to change -------------------------------------------- */
  var SETTINGS = {
    defaultHeight: 380,           // used if a figure has no data-height
    lazyLoadMargin: '400px 0px',  // start loading a chart this far before it scrolls into view
    embedOptions: {
      actions: false,             // hides the "..." menu (export, view source)
      renderer: 'svg',            // SVG text uses the page's web fonts and stays sharp when zoomed
      mode: 'vega-lite'
    }
  };

  /* ---------- Small helpers -------------------------------------------------------------- */

  /** Read a CSS custom property (design token) from :root, so charts and CSS share one palette. */
  function token(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  /** Copy of a spec's config merged under the shared base config. The spec's own config always wins. */
  function mergeConfig(base, own) {
    var out = JSON.parse(JSON.stringify(base));
    Object.keys(own || {}).forEach(function (key) {
      var a = out[key], b = own[key];
      out[key] = (a && b && typeof a === 'object' && typeof b === 'object' && !Array.isArray(a) && !Array.isArray(b))
        ? mergeConfig(a, b) : b;
    });
    return out;
  }

  /** Chart styling shared by every chart: fonts and neutral colours come from the CSS tokens. */
  function baseConfig() {
    var body = token('--font-body', 'sans-serif');
    var head = token('--font-head', 'serif');
    var text = token('--c-text', '#1F1B16');
    var muted = token('--c-text-muted', '#5A5348');
    var rule = token('--c-border', '#D9D1C4');
    // Vega wants a plain font-family string, so use the first named family from each stack.
    var bodyName = body.split(',')[0].replace(/["']/g, '').trim();
    var headName = head.split(',')[0].replace(/["']/g, '').trim();
    return {
      background: null,                       // transparent: the page colour shows through
      font: bodyName,
      view: { stroke: null },                 // no frame around the plot area
      axis: { labelFont: bodyName, titleFont: bodyName, labelColor: muted, titleColor: muted,
              labelFontSize: 13, titleFontSize: 13, domainColor: rule, tickColor: rule, gridColor: rule },
      legend: { labelFont: bodyName, titleFont: bodyName, labelColor: muted, titleColor: muted,
                labelFontSize: 13, titleFontSize: 13 },
      title: { font: headName, color: text, fontSize: 18, fontWeight: 600, anchor: 'start' },
      text: { font: bodyName, color: text }
    };
  }

  /**
   * Prepare a spec for the page: fit the width of the container, give it a height,
   * and merge in the shared config. Only fills in what the spec has not set itself.
   */
  function prepareSpec(spec, slot) {
    var s = JSON.parse(JSON.stringify(spec));
    var isMultiView = !!(s.hconcat || s.vconcat || s.concat || s.repeat || s.facet);
    if (!isMultiView) {
      if (s.width === undefined) s.width = 'container';
      if (s.height === undefined) s.height = Number(slot.dataset.height) || SETTINGS.defaultHeight;
      if (s.autosize === undefined) s.autosize = { type: 'fit-x', contains: 'padding' };
    }
    s.config = mergeConfig(baseConfig(), s.config);
    return s;
  }

  /** Turn a technical error into a sentence a reader (or you) can act on. */
  function explain(err, url) {
    var msg = String((err && err.message) || err);
    if (/HTTP 404/.test(msg)) return 'Spec file not found (' + url + '). It has not been built yet, or the file name is wrong.';
    if (/HTTP/.test(msg)) return 'Could not load ' + url + ' (' + msg + ').';
    if (/JSON/i.test(msg)) return 'The spec file ' + url + ' is not valid JSON (' + msg + ').';
    if (/Failed to fetch|NetworkError|Load failed/i.test(msg)) {
      return 'Could not fetch ' + url + '. If you opened this page by double-clicking the file, start a local server instead (see README).';
    }
    return 'The chart could not be drawn: ' + msg;
  }

  function showFallback(slot, url, err) {
    slot.classList.add('has-error');
    var status = slot.querySelector('.chart__status');
    if (status) status.textContent = 'Chart not shown. ' + explain(err, url);
    console.warn('[' + (slot.dataset.chart || slot.id) + '] ' + explain(err, url), err);
  }

  /* ---------- Loading one chart ---------------------------------------------------------- */
  var views = {};   // chart id -> Vega view, kept so later steps (for example linked charts) can reach it

  function loadChart(slot) {
    if (slot.dataset.state === 'loading' || slot.dataset.state === 'done') return Promise.resolve();
    slot.dataset.state = 'loading';

    var url = slot.dataset.spec;
    var target = slot.querySelector('.chart__canvas');
    if (!url || !target) { showFallback(slot, url || '(no data-spec set)', new Error('Chart slot is missing data-spec or .chart__canvas')); return Promise.resolve(); }
    if (typeof window.vegaEmbed !== 'function') {
      showFallback(slot, url, new Error('The Vega libraries did not load (check your internet connection).'));
      return Promise.resolve();
    }

    return fetch(url, { cache: 'no-cache' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (spec) {
        var ready = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
        return ready.then(function () { return window.vegaEmbed(target, prepareSpec(spec, slot), SETTINGS.embedOptions); });
      })
      .then(function (result) {
        views[slot.id] = result.view;
        slot.classList.remove('is-placeholder', 'has-error');
        slot.classList.add('is-loaded');
        slot.dataset.state = 'done';
      })
      .catch(function (err) {
        slot.dataset.state = 'failed';
        showFallback(slot, url, err);
      });
  }

  /* ---------- Start-up ------------------------------------------------------------------- */
  function init() {
    // Opened from a file? Browsers block fetch() there, so say so once, clearly.
    if (location.protocol === 'file:') {
      var banner = document.createElement('p');
      banner.className = 'page-banner';
      banner.setAttribute('role', 'status');
      banner.textContent = 'This page was opened as a file, so charts cannot load. Start a local server (python -m http.server) and open http://localhost:8000 instead.';
      document.body.insertBefore(banner, document.body.firstChild);
    }

    var slots = Array.prototype.slice.call(document.querySelectorAll('figure.chart[data-spec]'));

    // Give every slot its height as a CSS variable, so placeholder and chart take the same space.
    slots.forEach(function (slot) {
      slot.style.setProperty('--chart-h', (Number(slot.dataset.height) || SETTINGS.defaultHeight) + 'px');
    });

    // Handy in the browser console: DV.loadChart(document.getElementById('chart-c7')), DV.views
    window.DV = { loadChart: loadChart, views: views, prepareSpec: prepareSpec };

    if (!('IntersectionObserver' in window)) { slots.forEach(loadChart); return; }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { observer.unobserve(entry.target); loadChart(entry.target); }
      });
    }, { rootMargin: SETTINGS.lazyLoadMargin });
    slots.forEach(function (slot) { observer.observe(slot); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
