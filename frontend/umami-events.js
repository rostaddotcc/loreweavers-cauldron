/* Umami click events for dnd — passive observer.
   Never prevents default, never stops propagation: it can not break the page. */
(function () {
  var SEL = {"button[onclick*=\"rollNow\"]":  "roll-dice", "#export-campaign-item":  "export-campaign"};
  function track(name, data) {
    try {
      if (window.umami && typeof window.umami.track === 'function') window.umami.track(name, data);
    } catch (e) { /* never throw into the page */ }
  }
  document.addEventListener('click', function (e) {
    var node = e.target;
    if (!node || !node.closest) return;
    for (var sel in SEL) {
      if (node.closest(sel)) track(SEL[sel]);
    }
    var a = node.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.indexOf('mailto:') === 0) return track('contact-email');
    if (href.indexOf('tel:') === 0) return track('contact-phone');
    if (/^https?:/i.test(a.href) && a.hostname && a.hostname !== location.hostname) {
      track('outbound', { host: a.hostname });
    }
  }, true);
})();
