/**
 * 🎨 sprites.js — Pixel-art sprites som ersätter emojis
 * ------------------------------------------------------
 * Minskar mobil-app-känslan och landar i DOS/Castlevania-estetiken.
 * Varje sprite är ett handritat 8×8-rutnät som renderas som inline-SVG
 * med shape-rendering:crispEdges → skarpa pixlar i alla storlekar.
 *
 * En MutationObserver spritifierar allt dynamiskt innehåll automatiskt
 * (chatt-meddelanden, toasts, NPC-listor …) — ingen behöver anropa något.
 */
const SPR = (() => {
  // ── Palett (terminal-gothic) ──
  const PAL = {
    '.': null,          // transparent
    'k': '#0a0a12',     // svart
    'w': '#e0e0ec',     // vit / ben
    'd': '#6a6a80',     // dämpad grå
    's': '#a8b2c0',     // stål / silver
    'i': '#4a4a6a',     // järn
    'g': '#c9a227',     // guld
    'G': '#e8c65a',     // ljust guld
    'r': '#d43a4d',     // röd
    'R': '#8b1a2a',     // mörkröd
    'p': '#7b4fd4',     // lila
    'P': '#a88ae8',     // ljuslila
    'n': '#33cc33',     // grön
    'N': '#5a9a4e',     // dämpad grön
    'o': '#d4691e',     // eld / orange
    't': '#4e8a93',     // teal
    'b': '#8a6d3f',     // brun
    'B': '#5a4433',     // mörkbrun
    'f': '#e0b080',     // hud
    'c': '#33cccc',     // cyan
  };

  // ── 8×8 sprites (8 rader × 8 kolumner) ──
  const GRID = {
    '⚔': ['G......G','.s....s.','..s..s..','...ss...','...ss...','..s..s..','.s....s.','g......g'],
    '🔮': ['...pp...','..pPPp..','.pPwPPp.','.pPPPPp.','.pPPPPp.','..pPPp..','...pp...','..gggg..'],
    '📜': ['.gggggg.','.gwwwwg.','.gwddwg.','.gwwwwg.','.gwddwg.','.gwwwwg.','.gggggg.','........'],
    '🎭': ['.gggggg.','.gwwwwg.','.gkggkg.','.gwwwwg.','.gwggwg.','..gwwg..','...gg...','........'],
    '🗺': ['gggggggg','gwwdwwdg','gwddwrdg','gwwdrwdg','gwdwwddg','gwwdwwdg','gggggggg','........'],
    '🏰': ['g.gggg.g','gggggggg','.gggggg.','.gggggg.','.gg..gg.','.gggggg.','.gg..gg.','gggggggg'],
    '🕯': ['...oo...','...oo...','...ww...','...ww...','...ww...','...ww...','..gggg..','........'],
    '🐉': ['..nnnn..','.nnnnnn.','.nknnkn.','.nnnnnn.','..nnnn..','.nnnnnn.','n......n','........'],
    // ── Fiender (combat tokens, hashas på namn i chat.html) ──
    '🐗': ['..bbbb..','.bBBBBb.','bwbBBBwb','bbbbbbbb','.bbBBbb.','..bbbb..','.bb..bb.','........'],
    '🐺': ['..ssss..','.swwwss.','swksssss','ssssssss','..ssss..','.ss..ss.','ss....ss','........'],
    '🕷': ['...pp...','..p..p..','.p.p.p.p','..pppp..','.pprrpp.','..pppp..','.p.p.p.p','........'],
    '🦇': ['..r..r..','.rr..rr.','RRRRRRRR','RwrrrrwR','RRRRRRRR','.RR..RR.','........','........'],
    '👹': ['r..rr..r','RRRRRRRR','.rrrrrr.','.rRkkRr.','.rrrrrr.','.rrwwrr.','..rrrr..','........'],
    '🧟': ['..nnnn..','.nnnnnn.','.nkknnn.','.nnnnnn.','..nNNn..','.n....n.','........','........'],
    '🐀': ['..sss...','.sssss..','.sksss..','.sssss..','..sss...','...s....','..s.....','........'],
    '🦂': ['r...rr..','rr.rrr..','.rrrrr..','.rrrrr..','..rrr...','...r....','...r....','........'],
    '🧙': ['..pppp..','.pppppp.','.pppppp.','..ffff..','..fkfk..','.pppppp.','.pppppp.','........'],
    // Dungeon Master — guld-trollkarl med spetsig hatt (ZWJ-sekvens 🧙‍♂️, med och utan VS16)
    '🧙‍♂️': ['....G...','...GG...','..GGGG..','.GGGGGG.','..ffff..','..fkfk..','.GGGGGG.','.GGGGGG.'],
    '🧙‍♂': ['....G...','...GG...','..GGGG..','.GGGGGG.','..ffff..','..fkfk..','.GGGGGG.','.GGGGGG.'],
    '🎲': ['.wwwwww.','.wkwwkw.','.wwwwww.','.wwkwww.','.wwwwww.','.wkwwkw.','.wwwwww.','........'],
    '✨': ['...G....','..GGG...','.GGGGG..','..GGG...','...G....','.G......','.G.G....','........'],
    '📖': ['.RRRRRR.','.RwwwwR.','.RwddwR.','.RwwwwR.','.RwddwR.','.RwwwwR.','.RRRRRR.','........'],
    '🛡': ['.ssssss.','.sggggs.','.sggggs.','.ssssss.','..ssss..','...ss...','....s...','........'],
    '🔊': ['..ii....','.iinn...','.iinn.G.','.iinn..G','.iinn.G.','.iinn...','..ii....','........'],
    '🚪': ['.bbbbbb.','.bbbbb..','.bbbbb..','.bbgbb..','.bbbbb..','.bbbbb..','.bbbbbb.','........'],
    '🏹': ['..bb..s.','.b..b.s.','b....bs.','b....bs.','b....bs.','.b..b.s.','..bb..s.','........'],
    '💀': ['..wwww..','.wwwwww.','.wkwwkw.','.wwwwww.','..wwww..','..w.w.w.','..wwww..','........'],
    '📄': ['.wwwww..','.wwwwwg.','.wwwww..','.wddww..','.wwwww..','.wddww..','.wwwww..','........'],
    '🖼': ['.gggggg.','.gwwwwg.','.gwttwg.','.gwttwg.','.gwwwwg.','.gggggg.','........','........'],
    '📦': ['.bbbbbb.','.bBbbBb.','.bbbbb..','.bbgbb..','.bbbbb..','.bBbbBb.','.bbbbbb.','........'],
    '📍': ['...rr...','..rrrr..','..rkkr..','..rrrr..','...rr...','...r....','...r....','........'],
    '❓': ['..gggg..','.gggggg.','.gg..gg.','.....gg.','....gg..','...gg...','........','...gg...'],
    '⚑': ['.s......','.srrrr..','.srrrr..','.srrrr..','.s......','.s......','.s......','........'],
    '🗡': ['......s.','.....ss.','....ss..','...ss...','..ss....','.gg.....','.g......','........'],
    '📥': ['...s....','...s....','..sss...','.sssss..','sssssss.','.bbbbb..','.bbbbbb.','........'],
    '🩸': ['...r....','...r....','..rrr...','.rrrrr..','.rrrrr..','..rrr...','........','........'],
    '📎': ['..sss...','.s...s..','.s...s..','.s...s..','.s...s..','..sss...','........','........'],
    '🪙': ['..gggg..','.gGGGGg.','.gGggGg.','.gGggGg.','.gGGGGg.','..gggg..','........','........'],
    '🗑': ['..ssss..','.ssssss.','.s.ss.s.','.s.ss.s.','.s.ss.s.','.ssssss.','........','........'],
    '🎒': ['..bbbb..','.bbbbbb.','.bbggbb.','.bbbbbb.','.bBbbBb.','.bbbbbb.','........','........'],
    '📂': ['.gggg...','.gggggg.','.gwwwwg.','.gwwwwg.','.gggggg.','........','........','........'],
    '🔇': ['..ii....','.iinn..r','.iinn.r.','.iinn.r.','.iinn..r','..ii....','........','........'],
    '📕': ['.RRRRRR.','.RRRRRg.','.Rwwwwg.','.RRRRRg.','.RRRRRR.','........','........','........'],
    '🔒': ['..gggg..','.gg..gg.','.gg..gg.','.gggggg.','.gggggg.','.ggkggg.','.gggggg.','........'],
    '🌫': ['........','.ddddd..','........','..ddddd.','........','.ddddd..','........','........'],
    '⚡': ['...GG...','..GG....','.GGGGG..','...GG...','..GG....','.GG.....','........','........'],
    '⭐': ['...G....','...G....','..GGG...','.GGGGG..','..GGG...','..G.G...','.G...G..','........'],
    '💬': ['.wwwwww.','.wwwwww.','.wddddw.','.wwwwww.','...ww...','...w....','........','........'],
    '🪓': ['..ssss..','.sssss..','.ssss...','...b....','...b....','...b....','...b....','........'],
    '👊': ['..ffff..','.ffffff.','.ffffff.','.ffffff.','..ffff..','........','........','........'],
    '🌿': ['..N..N..','...NN...','..NN....','...NN...','....N...','....N...','...N....','........'],
    '🐍': ['..nnn...','.n...n..','.n......','.nnnn...','.....n..','.n...n..','..nnn...','........'],
    '❤': ['.rr..rr.','rrrrrrrr','rrrrrrrr','.rrrrrr.','..rrrr..','...rr...','........','........'],
    '📷': ['..ssss..','.ssssss.','.sskkss.','.skwwks.','.skwwks.','.ssssss.','........','........'],
    '📅': ['.gggggg.','.gggggg.','.wwwwww.','.wdwdww.','.wwwwww.','.wdwdww.','.wwwwww.','........'],
    '💡': ['...GG...','..GGGG..','..GwwG..','..GGGG..','...GG...','...ss...','...ss...','........'],
    '🔥': ['...o....','..oo....','..ooo...','.ooooo..','.ooGoo..','..ooo...','...o....','........'],
    '🔑': ['..ggg...','.g...g..','.g...g..','..ggg...','....g...','....gg..','....g...','....gg..'],
    '🛤': ['.b....b.','.b.ss.b.','.b.ss.b.','.b.ss.b.','.b.ss.b.','.b....b.','........','........'],
    '🥾': ['..bb....','..bb....','..bb....','..bbbb..','..bbbbb.','.bbbbbb.','........','........'],
    '🌲': ['...N....','..NNN...','.NNNNN..','..NNN...','.NNNNN..','...b....','...b....','........'],
    '⛰': ['....w...','...www..','..ddddd.','.ddddddd','dddddddd','........','........','........'],
    '🌾': ['..G.G...','..G.G...','...G....','...G....','...G....','...G....','........','........'],
    '❄': ['...w....','.w.w.w..','..www...','.wwwww..','..www...','.w.w.w..','...w....','........'],
    '🌊': ['........','.tt..tt.','tttttttt','.tttttt.','..tttt..','........','........','........'],
    '🚶': ['...ff...','...ff...','..bbbb..','...bb...','...bb...','..b..b..','..b..b..','........'],
    '🏠': ['...rr...','..rrrr..','.rrrrrr.','.bbbbbb.','.bbwwbb.','.bbwwbb.','.bbbbbb.','........'],
    '🕰': ['..gggg..','.gwwwwg.','.gwwswg.','.gwwswg.','.gwwwwg.','..gggg..','........','........'],
    '🗝': ['.ggg....','g...g...','g...g...','.ggg....','...g....','...gg...','...g....','........'],
    '🌒': ['...GGG..','..GG....','.GG.....','.GG.....','.GG.....','..GG....','...GGG..','........'],
    '⚖': ['..ssss..','....s...','..s.s.s.','.ss.s.ss','.s..s..s','....s...','...sss..','........'],
    '📚': ['.RRRR...','.RRRR...','.ppppp..','.ppppp..','.tttttt.','.tttttt.','........','........'],
    '🗣': ['..ffff..','.ffffff.','.fkffkf.','.ffffff.','..ffff..','...ff...','........','........'],
    '👁': ['........','..wwww..','.wppppw.','.wpkkpw.','.wppppw.','..wwww..','........','........'],
    '🏔': ['....w...','...www..','..wwwww.','.ddddddd','dddddddd','........','........','........'],
    '🌑': ['..dddd..','.dddddd.','.dddddd.','.dddddd.','.dddddd.','..dddd..','........','........'],
    '✅': ['........','......n.','.....nn.','.n..nn..','.nn.nn..','..nnn...','...n....','........'],
    '❌': ['.r....r.','.rr..rr.','..rrrr..','...rr...','..rrrr..','.rr..rr.','.r....r.','........'],
    '🎉': ['...G....','..G.G...','.G.G.G..','..rrr...','..rrr...','...rr...','...rr...','........'],
    '🤝': ['........','.ff..ff.','.ffffff.','..ffff..','..ffff..','........','........','........'],
    '🔄': ['..sss...','.s...s..','.s......','.s...s..','.s...s..','..sss...','........','........'],
    '🎯': ['..rrrr..','.rwwwwr.','.rwrrwr.','.rwrrwr.','.rwwwwr.','..rrrr..','........','........'],
    '🪶': ['.....w..','....ww..','...ww...','..ww....','.ww.....','.ww.....','.w......','........'],
    '💾': ['.ssssss.','.ssssss.','.ss..ss.','.ssssss.','.skssks.','.ssssss.','........','........'],
    '🌐': ['..tttt..','.tttttt.','.ttwttt.','.tttttt.','.tttttt.','..tttt..','........','........'],
    '🪟': ['.bbbbbb.','.bwwwwb.','.bwbbwb.','.bwwwwb.','.bwwwwb.','.bbbbbb.','........','........'],
    '🎵': ['....ss..','....ss..','....ss..','....ss..','..ssss..','..sss...','........','........'],
    '🌙': ['...GG...','..GG....','.GG.....','.GG.....','.GG.....','..GG....','...GG...','........'],
    '☀': ['...G....','.G.G.G..','..GGG...','.GGGGG..','..GGG...','.G.G.G..','...G....','........'],
    '🏘': ['.rr..rr.','rrrrrrr.','.bbbb.b.','.bwbbwb.','.bbbb.b.','........','........','........'],
    '⚠': ['...GG...','..GGGG..','.GGGGGG.','.GGkkGG.','.GGGGGG.','GGGkkGGG','........','........'],
  };

  // Text-symboler som får vara kvar (monokroma, ser redan CLI ut)
  const KEEP = new Set(['✦','✕','✓','♀','♫','♪','⚜']);

  // Emoji-regex (inkl. ZWJ-sekvenser som 🧙‍♀️ och variation selectors som ❤️)
  const EMOJI_RE = /(?:[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F1E6}-\u{1F1FF}]\uFE0F?)(?:\u200D[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]\uFE0F?)*/gu;

  // ── SVG-cache ──
  const cache = {};

  function svgFor(ch) {
    if (cache[ch]) return cache[ch];
    const rows = GRID[ch];
    if (!rows) return null;
    const grid = rows.join('');
    let rects = '';
    for (let i = 0; i < 64; i++) {
      const color = PAL[grid[i]];
      if (!color) continue;
      rects += '<rect x="' + (i % 8) + '" y="' + Math.floor(i / 8) +
               '" width="1" height="1" fill="' + color + '"/>';
    }
    cache[ch] = '<svg class="pxs" viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true">' +
                rects + '</svg>';
    return cache[ch];
  }

  function svgEl(ch) {
    const html = svgFor(ch);
    if (!html) return null;
    const tpl = document.createElement('template');
    tpl.innerHTML = html;
    return tpl.content.firstChild;
  }

  // Bas-emoji för en matchad token (hanterar ZWJ + VS16)
  function baseOf(token) {
    return String.fromCodePoint(token.codePointAt(0));
  }

  // ── Ersätt emojis i en sträng → HTML med sprites ──
  function html(str) {
    return String(str).replace(EMOJI_RE, (m) => {
      const base = baseOf(m);
      if (KEEP.has(base)) return m;
      const svg = svgFor(base);
      return svg || m;
    });
  }

  // ── Spritifiera en textnod ──
  function spritizeTextNode(tn) {
    const val = tn.nodeValue;
    if (!val || !EMOJI_RE.test(val)) { EMOJI_RE.lastIndex = 0; return; }
    EMOJI_RE.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m, replaced = false;
    while ((m = EMOJI_RE.exec(val)) !== null) {
      const base = baseOf(m[0]);
      if (KEEP.has(base)) continue;
      // Prova hela token först (t.ex. 🧙‍♂️ → guld-trollkarl), annars bas-emoji
      const el = svgEl(m[0]) || svgEl(base);
      if (!el) continue;
      if (m.index > last) frag.appendChild(document.createTextNode(val.slice(last, m.index)));
      frag.appendChild(el);
      last = m.index + m[0].length;
      replaced = true;
    }
    if (!replaced) return;
    if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
    tn.parentNode.replaceChild(frag, tn);
  }

  // ── Spritifiera alla textnoder under en rot ──
  function spritize(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(spritizeTextNode);
  }

  // ── Starta: spritifiera statiskt innehåll + övervaka dynamiskt ──
  function init() {
    if (!document.body) return;
    spritize(document.body);
    const obs = new MutationObserver(muts => {
      muts.forEach(m => {
        m.addedNodes.forEach(nd => {
          if (nd.nodeType === 3) spritizeTextNode(nd);
          else if (nd.nodeType === 1) spritize(nd);
        });
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { html, spritize, svgFor };
})();
