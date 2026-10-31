---
name: okabebot-character
description: Add or refine a Little Lab character's directory-owned art, avatar, prompts, motion, voice defaults and scene interfaces. Use for this repository's characters, not ChatGPT Pets.
---

Implement one character directory under `okabebot/characters/<id>/`. Read
[the character contract](../../../docs/character-animation.md#character-directory-contract)
and inspect the closest existing rig. Okabe/Kurisu are the reference implementations
for anchored paper/computer work; Sonic/Pip retain their current simpler motion.

- Export `CHARACTER`, an instance of a `Character` subclass in `__init__.py`, and
  implement `shapes(**state)` in the character's own `art.py`. Keep drawing pure,
  Python 3.7 compatible and independent of controller/network/hardware I/O.
- Own `character.json`, `avatar.json`, `motion.json`, `voice.json`, `portrait.png`,
  `persona.md` and `welcome-persona.md` in that directory. Runtime discovery uses
  the directory; do not add a parallel character switch or copy prompts into globals.
- Character identity must match the directory. Declare supported capabilities,
  existing scene choices, body primitives/head crop and default voice/reference key.
  New environments or rig capabilities are separate shared-engine changes.
- Keep prompt templates readable. Static text is compacted before strict substitution;
  source/user data must remain literal and cannot override permission/tool policy.
- Voice recordings/transcripts belong in ignored private storage, ideally grouped
  by character. `voice.json` contains only the private manifest lookup key/default;
  never import private audio, transcripts, account data or participant results into git.
- Art uses attached shoulders/elbows/wrists and consistent pixel grids. A writing
  pose grips a pencil whose nib touches desk-bound paper; a computer pose uses both
  hands on keys and looks toward the monitor. Fixtures should catch detached limbs,
  duplicate resting arms, moving furniture and invalid transition rectangles.
- Own notification arm anchors in `avatar.json`; wrists must meet the moving card
  throughout its entrance/exit. Keep facial clocks independent of presentation and
  cover reduced motion, withdrawal and interrupted replacement.
- Motion must yield to conversation, handoff, focus, notifications and media. Respect
  ambient/reduced-motion settings and short work leases. Decorative activity must not
  claim an order/action completed or invent real task progress.

Run character registry/directory-discovery, render, motion parity and relevant browser
regressions. Build the controller wheel and standalone satellite bundle; smoke-test
imports from the bundle without the controller package. Preview art locally before
hardware use. Update README/deployment inventory with source versus installed scope.
Deploy only within the requested scope and preserve rollback, private config, active
volume and voice-worker state. Request physical acceptance only for behavior that
cannot be verified remotely.
