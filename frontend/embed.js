// embed.js — döljer sidans egen topbar när den laddas inuti Codex-iframe.
// Codex-panelen har redan sin egen header + flikar (Character / NPCs / Map /
// Journal / Facts), så sidans egen navigering ("To the Table", "Logbook",
// "The Map", "NPCs", "Leave") blir duplication och tas bort.
// Aktiv endast när fönstret faktiskt är inbäddat i en iframe.
(function () {
  var embedded = true;
  try {
    embedded = window.self !== window.top;
  } catch (e) {
    embedded = true; // cross-origin → betrakta som inbäddad
  }
  if (!embedded) return;

  var hide = function () {
    // Rail v2 (2026-09-23): sidorna bär nu header.rite-rail utan .topbar —
    // matcha båda så gamla som nya headers döljs i Codex-iframen.
    document.querySelectorAll('header.topbar, header.rite-rail').forEach(function (el) {
      // !important krävs: rail.css har .rite-rail{display:grid!important} som
      // annars vinner över inline display:none.
      el.style.setProperty('display', 'none', 'important');
    });
    document.body.classList.add('embedded');

    // Codex-läsbarhet (2026-10-01): rostad ville ha allt i Codex "ett snäpp
    // större och lättläst". DELTA-bump (+1px) på både root och body — sidorna
    // har olika bas (facts.html står redan på 17px, andra på browserns 16px),
    // så ett fast värde skulle ge noll effekt på facts. Root-skalan driver
    // alla rem-baserade --fs-*-tokens, body-skalan allt som ärver px. Gäller
    // ENDAST inbäddat läge (.in-codex), så fristående besök behåller sin bas.
    // ASCII-kartans <pre> i platser.html skalar med, men mapInitView() mäter
    // offsetWidth i runtime och räknar om fit-skalan → ingen alignment-skada.
    document.documentElement.classList.add('in-codex');
    try {
      var _win = document.defaultView || window;
      var _rootPx = parseFloat(_win.getComputedStyle(document.documentElement).fontSize) || 16;
      document.documentElement.style.setProperty('font-size', (_rootPx + 1) + 'px');
      if (document.body) {
        var _bodyPx = parseFloat(_win.getComputedStyle(document.body).fontSize) || _rootPx;
        document.body.style.setProperty('font-size', (_bodyPx + 1) + 'px');
      }
    } catch (_) { /* beräknad stil misslyckades — hoppa över bump, ingen skada */ }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hide);
  } else {
    hide();
  }
})();
