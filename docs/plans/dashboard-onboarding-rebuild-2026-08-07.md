# Dashboard + Onboarding Rebuild (2026-08-07)

Checkpoint commit before work: `8db4f59`.

## Task A — archetypes.js (subagent 1)
- Add `cat` field to all 12 existing entries: 9 light → `'other'`, 3 dark → `'dark'` (keep `dark:true`).
- NEW: 6 classic archetypes (`cat:'classic'`) — iconic D&D staples not already covered (berserker, monk, war-priest, battle mage, dragonborn knight, gnome artificer …).
- NEW: 6 "Something Else Entirely" (`cat:'weird'`) — non-high-fantasy: cyberpunk, space, modern occult, post-apoc, far future, jazz-age. Prompt maps concept onto 5e sheet.
- NEW: 3 dark (`cat:'dark'`, `dark:true`) — same psychological-horror tone as psycho/serial/sadist, no explicit content.
- Full SV + EN content per entry, same schema as existing.

## Task B — newgame.html onboarding (subagent 2)
- Replace flat archetype grid + NSFW dropdown with 4 collapsible category sections:
  1. ⚔️ Classic Archetypes (open by default)
  2. 🌌 Something Else Entirely
  3. 🎭 Others (existing 9)
  4. 🖤 The Dark Path (collapsed, 18+ chip, blood styling)
- Keep: language select, Vault, Fateweave, summon flow, preview, tier gating.
- `.dark-select` CSS class is shared with language dropdown → keep class, remove only `.dark-drop*`.
- Collapse state in localStorage. Bump archetypes.js?v= cache tag.
- Tolerate missing `cat` (fallback 'other') — archetypes.js edited in parallel.

## Task C — admin.html CEO dashboard (subagent 3)
- Typography overhaul: nothing readable below ~0.75rem, base 15px, KPI numbers 2rem+.
- Collapsible sections (Realm KPIs / Dashboard charts / Player Accounts / Feedback), state in localStorage, expand/collapse-all.
- User list: pagination 10/page (desktop table + mobile cards), prev/next + numbered pages.
- Preserve ALL endpoints + action functions (topUp, setCap, grantTier, setRole, resetTurns, deleteUser, createUser, togglePremium, grantPremiumFromRow, toggleDetail, charts, revenue toggle, filters).
- Surgical patching, not full rewrite.

## Wave 2 — integration (Hästis)
- deploy-frontend.sh: copy all frontend/*.js (archetypes.js was missed → stale in container).
- Bump archetypes.js cache tag in adventure.html.
- Deploy to loreweavers-cauldron (:8092), visual verify admin + newgame, pytest backend, commit.
