/**
 * 🪟 modal.js — Mörk fantasy bekräftelsemodal
 * Användning: Modal.confirm({ title, body, danger, onConfirm })
 */
const Modal = (() => {
  // Injecta CSS en gång
  const style = document.createElement('style');
  style.textContent = `
    .modal-overlay {
      position: fixed; inset: 0; z-index: 100; display: none;
      align-items: center; justify-content: center;
      background: rgba(4,2,8,.85); backdrop-filter: blur(4px);
      animation: modal-fade .3s ease;
    }
    .modal-overlay.show { display: flex; }
    @keyframes modal-fade { from { opacity: 0; } to { opacity: 1; } }
    .modal-box {
      position: relative; width: 90%; max-width: 440px;
      background: linear-gradient(165deg, var(--stone-2, #1d1529), var(--stone, #161020) 55%, #120c1c);
      border: 1px solid var(--edge, #3d2f52); padding: 2rem 1.8rem 1.6rem;
      box-shadow: 0 30px 80px -20px rgba(0,0,0,.9), 0 0 40px -10px rgba(139,95,212,.15);
      animation: modal-rise .35s cubic-bezier(.22,1,.36,1);
    }
    @keyframes modal-rise { from { opacity: 0; transform: translateY(20px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
    .modal-box .corner { position: absolute; width: 16px; height: 16px; border-style: solid; opacity: .7; }
    .modal-box .corner.tl { top: 5px; left: 5px; border-width: 2px 0 0 2px; }
    .modal-box .corner.tr { top: 5px; right: 5px; border-width: 2px 2px 0 0; }
    .modal-box .corner.bl { bottom: 5px; left: 5px; border-width: 0 0 2px 2px; }
    .modal-box .corner.br { bottom: 5px; right: 5px; border-width: 0 2px 2px 0; }
    .modal-box:not(.danger) .corner { border-color: var(--gold, #c9a227); }
    .modal-box.danger .corner { border-color: var(--blood-bright, #d43a4d); }
    .modal-icon { text-align: center; font-size: 2.2rem; margin-bottom: .8rem; }
    .modal-title {
      font-family: 'Cinzel', serif; font-weight: 900; font-size: 1.2rem;
      text-align: center; margin-bottom: .7rem; letter-spacing: .04em;
    }
    .modal-box:not(.danger) .modal-title { color: var(--bone-bright, #efe2c0); }
    .modal-box.danger .modal-title { color: var(--blood-bright, #d43a4d); text-shadow: 0 0 16px rgba(212,58,77,.4); }
    .modal-body {
      font-family: 'Spectral', serif; font-size: .9rem; line-height: 1.65;
      color: var(--bone, #d9c9a6); text-align: center; margin-bottom: 1.5rem;
    }
    .modal-body em { color: var(--bone-dim, #8a7a5e); }
    .modal-actions { display: flex; gap: .8rem; justify-content: center; }
    .modal-btn {
      font-family: 'Cinzel', serif; font-weight: 700; font-size: .72rem;
      letter-spacing: .14em; text-transform: uppercase; cursor: pointer;
      padding: .75rem 1.5rem; border-radius: 2px; transition: all .2s;
    }
    .modal-btn.cancel {
      background: var(--stone-3, #241a33); border: 1px solid var(--edge, #3d2f52);
      color: var(--bone-dim, #8a7a5e);
    }
    .modal-btn.cancel:hover { color: var(--bone-bright, #efe2c0); border-color: var(--bone-dim); }
    .modal-btn.confirm {
      border: 1px solid #6e5510; color: #1a1206;
      background: linear-gradient(180deg, var(--gold-bright, #e8c65a), var(--gold, #c9a227) 55%, #8a6d14);
      box-shadow: 0 4px 14px -4px rgba(232,198,90,.5);
    }
    .modal-btn.confirm:hover { filter: brightness(1.12); transform: translateY(-2px); }
    .modal-box.danger .modal-btn.confirm {
      background: linear-gradient(180deg, var(--blood-bright, #d43a4d), var(--blood, #a32433) 55%, #6e1520);
      border-color: #6e1520; color: #fff;
      box-shadow: 0 4px 14px -4px rgba(212,58,77,.5);
    }
  `;
  document.head.appendChild(style);

  let overlay = null;

  function build() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box" id="modal-box">
        <i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>
        <div class="modal-icon" id="modal-icon"></div>
        <div class="modal-title" id="modal-title"></div>
        <div class="modal-body" id="modal-body"></div>
        <div class="modal-actions">
          <button class="modal-btn cancel" id="modal-cancel">Avbryt</button>
          <button class="modal-btn confirm" id="modal-confirm">Bekräfta</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    // Stäng vid klick utanför
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    document.getElementById('modal-cancel').addEventListener('click', close);
    return overlay;
  }

  function close() {
    if (overlay) overlay.classList.remove('show');
  }

  return {
    /**
     * Visa bekräftelsemodal. Returnerar Promise<boolean>.
     * @param {Object} opts
     * @param {string} opts.title - Rubrik
     * @param {string} opts.body - Brödtext (HTML tillåtet)
     * @param {string} [opts.icon] - Emoji-ikon
     * @param {string} [opts.confirmText] - Bekräfta-knapptext
     * @param {string} [opts.cancelText] - Avbryt-knapptext
     * @param {boolean} [opts.danger] - Röd danger-variant
     * @param {Function} [opts.onConfirm] - Körs vid bekräftelse (valfritt, Promise räcker)
     * @returns {Promise<boolean>}
     */
    confirm({ title, body, icon = '⚔️', confirmText = 'Bekräfta', cancelText = 'Avbryt', danger = false, onConfirm }) {
      build();
      const box = document.getElementById('modal-box');
      box.classList.toggle('danger', danger);
      document.getElementById('modal-icon').textContent = icon;
      document.getElementById('modal-title').textContent = title;
      document.getElementById('modal-body').innerHTML = body;
      document.getElementById('modal-confirm').textContent = confirmText;
      document.getElementById('modal-cancel').textContent = cancelText;

      return new Promise(resolve => {
        // Ny confirm-knapp (ta bort gammal lyssnare)
        const btn = document.getElementById('modal-confirm');
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        newBtn.addEventListener('click', () => {
          close();
          if (onConfirm) onConfirm();
          resolve(true);
        });

        // Avbryt → resolve(false)
        const cancelBtn = document.getElementById('modal-cancel');
        const newCancel = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
        newCancel.addEventListener('click', () => { close(); resolve(false); });

        // Klick utanför → resolve(false)
        overlay.onclick = e => { if (e.target === overlay) { close(); resolve(false); } };

        overlay.classList.add('show');
      });
    },
    close,
  };
})();
