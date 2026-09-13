# composer-resize-journal — 2026-09-13
10:46 snes.css ~2301: .cli-prompt flex:0 1 auto + min-width:0 + overflow:hidden + ellipsis (squeeze-fix, även >900px nu)
10:46 snes.css ~2844: #player-input min-width:min(180px,46vw)!important; height:clamp(2.75rem,var(--composer-h),75vh)!important; padding-left 1.8rem; resize:none kvar
10:47 snes.css ~2868: .composer-splitter stil (8px, guld-grip, dashed-linje, ::after touch-yta, row-resize, z-index 3) + .main{--composer-h:max(15vh,90px)} + body.cli-chat .main{max(15vh,114px)} + body.composer-resizing
10:47 snes.css ~2996: mobil ≤768px #player-input height:clamp(3.4rem,var(--composer-h),75vh)!important
10:47 chat.html ~1613: <div class="composer-splitter" id="composer-splitter" role="separator" aria-orientation="horizontal" tabindex="0"> insatt före .input-area (mellan #chat och kompositören)
10:50 chat.html ~5346: input-listenern — Math.min(scrollHeight,140) borttagen, style.height='' (CSS äger höjden)
10:50 chat.html ~5566: sendPlayer() reset — style.height='' istället för 'auto'
10:50 chat.html ~8565: cdMentionNpc — 140px-kap borttagen
10:51 chat.html ~7793: applyCliChat() — återställer/återläser --composer-h vid lägesbyte (sparad höjd eller CSS-default)
10:51 chat.html ~8730: COMPOSER-SPLITTER-IIFE — pointerdrag+setPointerCapture, clamp 44px–75vh, dblclick=reset, piltangenter, resize-guard, persist 'composer-h-v1'
10:55 VALIDERING: node --check 3/3 scriptblock OK; snes.css {}=845/845; chat.html style {}=1095/1095; harness-test (file://): drag 114→214, min-clamp 44, max-clamp 475 (=75vh@633), dblclick→114+localStorage null, ArrowUp→126, restore-on-load 300→300, bubble-default 95px, CLI@1280x633 ta_w=810px (var 16px), resize:none kvar
