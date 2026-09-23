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
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hide);
  } else {
    hide();
  }
})();
