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
    document.querySelectorAll('header.topbar').forEach(function (el) {
      el.style.display = 'none';
    });
    document.body.classList.add('embedded');
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hide);
  } else {
    hide();
  }
})();
