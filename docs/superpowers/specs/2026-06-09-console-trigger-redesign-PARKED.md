# Console redesign → unified trigger-binding manager — PARKED

- **Status:** PARKED 2026-06-09 (brainstorm in progress, intentionally deferred)
- **Why parked:** decided to decompose the `PlayAIdes` god object *first* so the console lands on a
  clean contract. Resume this after the persona/trigger backend slice exists. See
  `2026-06-09-backend-frontend-architecture-redesign.md` (migration sequence).
- **Supersedes the UX of:** `2026-06-08-integrations-console-v1-design.md` (slice 1, shipped). The
  data/provider plumbing from slice 1 stays; this changes what the console *is*.

## The reframe

Slice-1's console is a thin **capability → HA entity** mapper (only the `pip` slot actually works;
`say_target`/`launch_targets`/`scripts` are an unbuilt hint line). That's too thin. The real unit of
configuration is the **full binding** that already exists in `persona.py`:

```
Trigger = { on: TriggerOn{ phrase | event, match }, do: TriggerDo{ skill, params } }
```

The console should become a **unified trigger-binding manager** — CRUD over these bindings.

## Decisions locked so far

1. **Unified trigger rows (chosen: option A).** Each row = one full binding:
   `{ persona-scope · trigger (phrase OR event) · action (skill) · target (params) }`.
   Maps 1:1 onto `persona.triggers`. The old pip/say/launch "mappings" become the *target* picked
   inside a row, not a separate concept.
2. **`+` button to add a new trigger row.** Rows are **editable and deletable** (full CRUD).
3. **The control-panel button is not fake — it's the `event` trigger path.** `skills/router.py`
   matches *phrase* triggers (voice) and *event* triggers (the `demo_camera` button) — two `on:`
   variants of the same Trigger. Voice is already first-class; the test button is the event variant.
4. **Trigger phrase = hardcoded default but editable** per binding.
5. **Worked example (the printer camera):** phrase `"show camera"` + location `"printer"` →
   `do.skill = show_pip`, `do.params.source = camera.printer_gym_camera_hd_stream` (a `pip` camera
   source). This is the "what makes it fire" (trigger) + "what it resolves to" (integration mapping)
   folded into one row.

## Two layers this unifies (keep clear when building)

- **Integration mappings** (slice 1): capability → HA entity — *what "printer" resolves to.* Lives in
  the `stores/` config store, exposed by `api/integrations.py`.
- **Persona triggers** (`persona.triggers`): phrase/event → skill → params — *what makes it fire.*
  Currently owned/persisted by the `PlayAIdes` god object (`update_persona` →
  `personas/<id>/persona.json`), with **no triggers store and no `/api/v1` triggers API yet.**

The unified row folds the target-selection (layer 1) into the binding (layer 2).

## Open questions (resolve when we resume)

- **"Any persona" scope.** The user wrote `[persona:name:any]`. Today triggers are nested *per
  persona*; a shared/"any persona" trigger does not exist in the model — needs a design decision
  (shared trigger list? a `scope` field on Trigger?).
- **LLM phrase-parsing vs deterministic prefix match.** `router.match_phrase_trigger` is deterministic
  (case-insensitive, word-boundary, prefix-only). The user wants LLM-parsed intent ("we have a live
  llm"). How do the two coexist — deterministic fast-path + LLM fallback? Where does parsing live
  (`ConversationService`)?
- **HA voice/intents overlap.** User: "HA already does something like this." `Persona` has
  `ha_agent_id` + `rephrase_ha_response`. Research where trigger parsing should live (playAIdes' own
  LLM pipeline vs HA Assist/intents) before committing the UX.
- **Backend prerequisite.** The console needs a **triggers store + `/api/v1` triggers endpoints**
  (mirroring slice-1's api→store pattern) carved out of `PlayAIdes`. This is exactly the
  persona/trigger slice of the god-object decomposition — which is why the console is parked behind it.
- **Pending "consume" rewire** (from the prior session): camera/pip + `/api/launch` + say-target must
  actually *read* the store. Still open; intersects the target-resolution half of a row.

## Resume condition

Resume this brainstorm once the persona/trigger backend slice (PersonaService + persona/trigger store +
`/api/v1` triggers API) exists, so the unified-row console has a clean contract to build against.
