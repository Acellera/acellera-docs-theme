// Acellera docs Mol* bootstrap.
// Loaded once per page (after molstar.js) via html_js_files. Finds every
// <div class="acellera-molstar" data-structure=... data-mvs=...>, injects the
// depth-correct structure URL into the MVS tree, and renders it.
(function () {
  "use strict";

  // Resolve the _static base from this script's own URL so structure URLs are
  // correct at any page depth (no inline scripts, no knowing the depth).
  var own = document.currentScript;
  if (!own) {
    var all = document.getElementsByTagName("script");
    for (var i = 0; i < all.length; i++) {
      if (all[i].src && all[i].src.indexOf("molstar/molstar-embed.js") !== -1) {
        own = all[i];
        break;
      }
    }
  }
  var base = own ? own.src.replace(/molstar\/molstar-embed\.js.*$/, "") : "";

  var VIEWER_OPTIONS = {
    layoutIsExpanded: false,
    layoutShowControls: false,
    layoutShowSequence: false,
    layoutShowLog: false,
    layoutShowLeftPanel: false,
    viewportShowExpand: true,
    viewportShowSelectionMode: false,
    viewportShowAnimation: false,
  };

  function initOne(div) {
    if (div.dataset.molstarInit) return;
    div.dataset.molstarInit = "1";
    var url = base + div.dataset.structure;
    // loadMvsData wants the mvsj STRING; just substitute the URL sentinel.
    var mvs = div.getAttribute("data-mvs").split("__STRUCTURE_URL__").join(url);
    molstar.Viewer.create(div, VIEWER_OPTIONS).then(function (viewer) {
      viewer.loadMvsData(mvs, "mvsj");
    });
  }

  function initAll() {
    if (typeof molstar === "undefined" || !molstar.Viewer) {
      setTimeout(initAll, 50);
      return;
    }
    var divs = document.querySelectorAll("div.acellera-molstar");
    for (var i = 0; i < divs.length; i++) initOne(divs[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
