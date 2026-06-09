# Avatar creator research — open-source in-app VRM model creation

**Date:** 2026-06-08 · **Floor:** must be **open source** (closed/SaaS tools rejected except as
contrast) · **Method:** multi-source deep research, adversarially fact-checked (23/25 claims
confirmed; 2 over-claims killed).

**The question:** playAIdes already has a working VRM + VRMA viewer and a "Persona Forge" page
that assigns *voice* and *animations* to a persona. The missing piece is model **creation** —
today that's done in the closed-source **VRoid Studio**. Can we let users create avatars
*in-project*, under a hard open-source floor?

---

## TL;DR — the finding that decides it

**VRM export is the hard blocker, and it's on our side of the fence.** `@pixiv/three-vrm` — the
library the viewer already uses — **cannot export VRM**. VRM's MToon material can't be serialized
by three.js's `GLTFExporter` (confirmed by maintainer 0b5vr,
[three-vrm discussion #1114](https://github.com/pixiv/three-vrm/discussions/1114); still
unimplemented as of v3.5.2). The official "arbitrary humanoid → VRM" path is **Unity+UniVRM** or
**Blender+VRM-Addon**, not browser-native.

Consequence: a from-scratch *in-browser* creator on our stack is **not possible today unless the
tool ships its own VRM exporter**. Also confirmed: **no open-source path produces a rigged VRM
humanoid in one step from text/photo** — AI generation isn't there yet under an OSS floor.

---

## Landscape (all OSS-floor-verified)

| Approach | Candidate | License | VRM output | Web/Three.js fit | Effort |
|---|---|---|---|---|---|
| **Web creator** | [CharacterStudio](https://github.com/M3-org/CharacterStudio) (M3-org) | **MIT** ✅ | **Native** ✅ | Yes — Three.js/React, in-browser, actively maintained | Med (embed) — **must supply an OSS wardrobe asset lib** |
| **Import+customize** | [vrm-avatar-editor](https://github.com/gatosyocora/vrm-avatar-editor) (gatosyocora) | **MIT** ✅ | re-export (WIP) | **Our exact stack** (three + @pixiv/three-vrm) | Low–med (build) — export is the snag; **abandoned 2021**, use as reference |
| **AI gen** | [UniRig](https://github.com/VAST-AI-Research/UniRig) (VAST-AI) | **MIT** ✅ (code+weights) | ❌ generic skeleton, *not* VRM humanoid | ❌ CUDA/Python only | High — backend + bone-mapping step |
| **AI gen** | Hunyuan3D-2.1 | ❌ Tencent license | n/a | n/a | **REJECTED** — excludes EU/UK/S.Korea, fails floor |
| **Parametric** | [MakeHuman / MPFB2](https://static.makehumancommunity.org/about/license.html) | assets **CC0** ✅ / app AGPL | ❌ no native (DAE/OBJ/FBX) | ❌ desktop/Blender | High — needs Blender→VRM |
| **Conversion engine** | [VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender) (saturday06) | **MIT or GPL-3.0** ✅ | **True rigged humanoid VRM** ✅ | Backend (headless Blender + Python API) | The backbone for any non-VRM source |

---

## Recommendation

**Primary — embed CharacterStudio.** It's the *only* OSS web tool that natively exports VRM, so it
sidesteps the export blocker entirely, and it's on a compatible Three.js stack. **Gating task:** it
ships no avatars (defaults are fantasy-RPG with unclear licensing), so we'd need to source or author
an OSS everyday-wardrobe/hair/body library — directly relevant to the project's redistribution care.

**Fallback — build a thin "import + customize" editor** on the existing `@pixiv/three-vrm` stack:
user brings a VRM (VRoid Studio is free for *end users* even though it's closed), then
recolors/edits materials/blendshapes/swaps outfits in-app. `vrm-avatar-editor` (MIT, exact stack)
is direct prior-art. **Snag:** re-saving needs a Blender backend — *or* limit to non-destructive
customization that never re-exports.

**Backend for everything else — FastAPI + headless Blender + VRM-Addon** as the universal "→VRM"
converter (handles MakeHuman output, UniRig, AI meshes). The piece that makes parametric/AI paths
viable later.

**AI generation — park it.** Not ready as a one-step OSS path; revisit when a permissively-licensed
image→rigged-VRM-humanoid model appears.

---

## VRoid Studio automation / MCP? (checked — no creation path)

Asked separately: could we drive VRoid Studio itself via an MCP/API instead of building a creator?
**No viable path.**

- **No creation API.** The official **VRoid SDK** is a Unity/Unreal package that links to **VRoid
  Hub** to *access existing published models* — the docs are explicit that *"you cannot create
  characters with the VRoid SDK."* There's no headless/CLI/automation surface for *building* a
  model in VRoid Studio, and no sign of a planned one.
- **Plugins are dead.** Community plugins (e.g. VRoidXYTool) broke when VRoid Studio switched
  mono→il2cpp at v1.26.1 and are hard to fix.
- **The one "VRoid MCP" that exists** is a hobbyist bridge for controlling avatar *expressions at
  runtime in Unity* (AI → MCP → Unity+VRoid) — puppeteering an already-made avatar, which overlaps
  what the playAIdes viewer already does, **not** model creation.

**Useful tangent (acquisition, not creation):** the **VRoid Hub API + SDK** (OAuth) *could* let
playAIdes *import* a model a user already published to VRoid Hub, carrying its license metadata — a
clean "pull in your existing VRoid avatar" path that respects VRoid licensing. It doesn't create
models, but it's a low-friction way to get a user's VRM in without manual file handling.

Sources: [VRoid SDK](https://developer.vroid.com/en/sdk/) ·
[VRoid Hub API](https://developer.vroid.com/en/api/) ·
[What is VRoid SDK (can't create)](https://vroid.pixiv.help/hc/en-us/articles/360011743973-What-is-VRoid-SDK) ·
[Vroid MCP (runtime expression control)](https://dev.to/webdeveloperhyper/how-to-make-ai-controled-avatar-2-vroid-mcp-cline-and-cursor-unity-2imk)

## Caveats
- CharacterStudio's **asset-pack licensing is the weakest verified point** — core app is solidly
  MIT, but the wardrobe libs (`loot-assets`/`character-assets`) show no clear LICENSE.
- MakeHuman's **CC0-on-output is conditional** (official unmodified GUI exports only); the app code
  itself is AGPL (only matters if reusing the code, not the exported models).
- `vrm-avatar-editor` is **abandoned** (Vue 2, pre-VRM-1.0) — reference, not a dependency.
- AI 3D-generation moves fast — re-check for new permissive text/image→rigged-VRM models before
  committing.

## Open questions (worth resolving before committing)
1. **Blender export feasibility:** can a headless Blender + VRM-Addon (FastAPI) pipeline reliably
   auto-map an *arbitrary* MakeHuman/UniRig skeleton to the VRM humanoid bone set **unattended**, or
   does it need per-model manual bone mapping? (Decides whether the fallback's export is cheap or
   painful.)
2. **OSS wardrobe:** is there an everyday-wardrobe (non-fantasy) OSS asset set that drops into
   CharacterStudio without redistribution risk, or must we author a CC0/MIT set?
3. **Front-end export route:** for a minimal import+customize editor on three-vrm v3.x, round-trip
   through a backend Blender/UniVRM service, or contribute the missing MToon `GLTFExporter` support
   (issue #1114)?

## Sources
- [CharacterStudio](https://github.com/M3-org/CharacterStudio) ·
  [vrm-avatar-editor](https://github.com/gatosyocora/vrm-avatar-editor) ·
  [UniRig](https://github.com/VAST-AI-Research/UniRig) ·
  [VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender)
- [three-vrm #1114 (no VRM export)](https://github.com/pixiv/three-vrm/discussions/1114) ·
  [vrm.dev — convert from humanoid model](https://vrm.dev/en/vrm/how_to_make_vrm/convert_from_humanoid_model/)
- [MakeHuman license](https://static.makehumancommunity.org/about/license.html) ·
  [Hunyuan3D-2.1 license](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE)
