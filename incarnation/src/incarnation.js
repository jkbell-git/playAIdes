import { scene, controls, setBackground, focusOnHead, frameFullBody } from './scene.js';
import { loadModel, loadAnimationFile, listMorphTargets } from './modelLoader.js';
import { loadMixamoAnimation } from './loadMixamoAnimation.js';
import { loadVRMAAnimation } from './vrmaLoader.js';
import { AnimationManager } from './animationManager.js';
import { ExpressionManager } from './expressionManager.js';
import { VisemeManager } from './visemeManager.js';
import { LipSyncManager } from './lipSyncManager.js';
import { retargetAnimation } from 'vrm-mixamo-retarget'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';
/**
 * Incarnation — top-level orchestrator for a single persona's 3D body.
 *
 * Owns one loaded model and all its associated managers.
 * Supports both standard glTF/GLB and VRM models.
 *
 * For VRM models, expressions are driven through the VRM expressionManager
 * (which handles preset expressions like happy, angry, surprised, etc.)
 * rather than raw morph targets.
 *
 * Future: multiple Incarnation instances for multi-persona support.
 */
export class Incarnation {
    constructor() {
        /** @type {import('three').Group|null} */
        this.model = null;

        /** @type {import('@pixiv/three-vrm').VRM|null} */
        this.vrm = null;

        /** @type {AnimationManager|null} */
        this.animationManager = null;

        /** @type {ExpressionManager} */
        this.expressionManager = new ExpressionManager();

        /** @type {VisemeManager} */
        this.visemeManager = new VisemeManager();

        /** @type {LipSyncManager} */
        this.lipSyncManager = new LipSyncManager(this.visemeManager);

        this._loaded = false;

        /** @type {Function|null} */
        this.onAnimationFinished = null;
    }

    /** Whether a model is currently loaded. */
    get isLoaded() {
        return this._loaded;
    }

    /** Whether the loaded model is a VRM. */
    get isVRM() {
        return this.vrm !== null;
    }

    /** Whether a one-shot (non-idle) animation is currently playing. */
    get isPlayingOneShot() {
        return this.animationManager?.isPlayingOneShot ?? false;
    }

    // ── Model lifecycle ─────────────────────────────────────────────────────

    /**
     * Load a persona's 3D model and wire up all managers.
     * @param {object} config
     * @param {string} config.url  Path or URL to glTF / GLB / VRM file.
     * @param {Function} [onProgress]
     */
    async loadPersona(config, onProgress) {
        // Unload previous model if any
        this.unload();

        const { model, clips, skinnedMeshes, vrm } = await loadModel(config.url, onProgress);
        this.model = model;
        this.vrm = vrm;
        scene.add(model);

        // Wire up managers
        this.animationManager = new AnimationManager(model, (clipName) => {
            if (this.onAnimationFinished) {
                this.onAnimationFinished(clipName);
            }
        });
        if (clips.length > 0) {
            this.animationManager.loadClips(clips);
        }

        this.expressionManager.setMeshes(skinnedMeshes);
        this.visemeManager.setMeshes(skinnedMeshes);
        if (vrm && vrm.expressionManager) {
            this.visemeManager.setExpressionManager(vrm.expressionManager);
        }

        this._loaded = true;

        // Log what's available
        const info = this._getModelInfo(skinnedMeshes);
        console.log('[Incarnation] Model loaded:', config.url);
        console.log('[Incarnation] Type:', this.isVRM ? 'VRM' : 'glTF/GLB');
        console.log('[Incarnation] Animations:', info.animations);
        console.log('[Incarnation] Morph targets:', info.morphTargets);
        if (this.isVRM) {
            console.log('[Incarnation] VRM expressions:', info.vrmExpressions);
        }

        return info;
    }

    /**
     * Load a standalone animation file and register its clips.
     * @param {object} config
     * @param {string} config.url   Path or URL to animation file (FBX/GLB/glTF).
     * @param {string} [config.name]  Optional override name for the clip(s).
     */
    async loadAnimation(config) {
        if (!this.animationManager) {
            console.warn('[Incarnation] No model loaded — load a model before loading animations');
            return { animations: [] };
        }

        const clips = await loadAnimationFile(config.url);

        // Optionally rename clips to a user-specified name
        if (config.name && clips.length > 0) {
            // If there's only one clip, rename it directly.
            // If multiple, suffix with _0, _1, etc.
            if (clips.length === 1) {
                clips[0].name = config.name;
            } else {
                clips.forEach((clip, i) => {
                    clip.name = `${config.name}_${i}`;
                });
            }
        }

        this.animationManager.loadClips(clips);

        const names = clips.map((c) => c.name);
        console.log('[Incarnation] Animation loaded:', config.url, '→', names);

        return {
            animations: this.animationManager.listClips(),
            loaded: names,
        };
    }

    /**
     * Load a Mixamo animation file.
     * For VRM models, bone tracks are automatically retargeted via the
     * Mixamo → VRM rig map. For non-VRM models, falls back to generic loading.
     *
     * @param {object} config
     * @param {string} config.url   Path or URL to a Mixamo FBX animation file.
     * @param {string} [config.name]  Optional override name for the clip.
     */
    async loadMixamoAnim(config) {
        if (!this.animationManager) {
            console.warn('[Incarnation] No model loaded — load a model before loading animations');
            return { animations: [] };
        }

        let clip;

        if (this.isVRM) {
            const fbxLoader = new FBXLoader();
            const fbxAsset = await fbxLoader.loadAsync(config.url);
            // Use VRM-aware retargeting
            clip = retargetAnimation(fbxAsset, this.vrm);
            //clip = await loadMixamoAnimation(config.url, this.vrm);
        } else {
            // Fallback: load generically (no retargeting needed)
            const clips = await loadAnimationFile(config.url);
            clip = clips[0] || null;
        }

        if (!clip) {
            console.warn('[Incarnation] No animation clip found in:', config.url);
            return { animations: this.animationManager.listClips(), loaded: [] };
        }

        // Apply optional name override
        if (config.name) {
            clip.name = config.name;
        }

        this.animationManager.loadClips([clip]);

        console.log('[Incarnation] Mixamo animation loaded:', config.url, '→', clip.name);

        return {
            animations: this.animationManager.listClips(),
            loaded: [clip.name],
        };
    }

    /**
     * Load a VRMA animation file (native VRM animation format).
     * Only works with VRM models.
     *
     * @param {object} config
     * @param {string} config.url   Path or URL to a .vrma file.
     * @param {string} [config.name]  Optional override name for the clip.
     */
    async loadVRMAAnim(config) {
        if (!this.animationManager) {
            console.warn('[Incarnation] No model loaded — load a model before loading animations');
            return { animations: [] };
        }

        if (!this.isVRM) {
            console.warn('[Incarnation] VRMA files can only be applied to VRM models.');
            return { animations: this.animationManager.listClips(), loaded: [] };
        }

        const clip = await loadVRMAAnimation(config.url, this.vrm);

        if (!clip) {
            console.warn('[Incarnation] No VRMA clip loaded from:', config.url);
            return { animations: this.animationManager.listClips(), loaded: [] };
        }

        // Apply optional name override
        if (config.name) {
            clip.name = config.name;
        }

        this.animationManager.loadClips([clip]);

        console.log('[Incarnation] VRMA animation loaded:', config.url, '→', clip.name);

        return {
            animations: this.animationManager.listClips(),
            loaded: [clip.name],
        };
    }

    /**
     * Unload the currently-loaded VRM. Used during persona swap so the
     * scene is clean before the new VRM is loaded.
     */
    unloadModel() {
        if (this.vrm) {
            if (scene && this.vrm.scene) {
                scene.remove(this.vrm.scene);
            }
            this.vrm = null;
        }
        if (this.model) {
            if (scene && this.model.parent === scene) {
                scene.remove(this.model);
            }
            this.model = null;
        }
        if (this.animationManager) {
            this.animationManager.stop();
            this.animationManager = null;
        }
    }

    /** Remove the current model from the scene and reset managers. */
    unload() {
        if (this.model) {
            scene.remove(this.model);
            this.model = null;
        }
        this.vrm = null;
        this.animationManager = null;
        this.expressionManager.setMeshes([]);
        this.visemeManager.setMeshes([]);
        this._loaded = false;
    }

    // ── Command dispatch ────────────────────────────────────────────────────

    /**
     * Handle a command message (typically from ConnectionManager).
     * @param {string} type
     * @param {object} payload
     */
    async handleCommand(type, payload) {
        console.log('[Incarnation] Received command:', type, payload);
        switch (type) {
            case 'load_model':
                {
                    const result = await this.loadPersona({ url: payload.url });
                    // Apply optional spawn_point and camera_target from the
                    // persona's avatar config (Phase 5). Defaults match today's
                    // behavior when omitted.
                    if (Array.isArray(payload.spawn_point) && payload.spawn_point.length === 3 && this.vrm) {
                        const [x, y, z] = payload.spawn_point;
                        this.vrm.scene.position.set(x, y, z);
                    }
                    if (Array.isArray(payload.camera_target) && payload.camera_target.length === 3) {
                        const [x, y, z] = payload.camera_target;
                        // controls is imported at the top of incarnation.js from scene.js.
                        controls.target.set(x, y, z);
                        controls.update();
                    }
                    return result;
                }

            case 'unload_model':
                this.unloadModel();
                return { unloaded: true };

            case 'load_animation':
                return await this.loadAnimation({
                    url: payload.url,
                    name: payload.name,
                });

            case 'load_mixamo_animation':
                return await this.loadMixamoAnim({
                    url: payload.url,
                    name: payload.name,
                });

            case 'load_vrma_animation':
                return await this.loadVRMAAnim({
                    url: payload.url,
                    name: payload.name,
                });

            case 'play_animation':
                if (!this.animationManager) break;
                this.animationManager.play(payload.name, {
                    loop: payload.loop ?? true,
                    crossFadeDuration: payload.crossFade ?? 0.4,
                });
                // One-shot animations (intros/gestures) often use the full body —
                // zoom out so it isn't clipped. Looping idles keep the bust framing.
                // In kiosk the camera director owns framing, so this is a no-op there.
                if (payload.loop === false && this.model) {
                    frameFullBody(this.model);
                }
                break;

            case 'stop_animation':
                if (this.animationManager) this.animationManager.stop();
                break;

            case 'set_expression':
                this._setExpressions(payload.expressions || {});
                break;

            case 'clear_expressions':
                this._clearExpressions();
                break;

            case 'play_viseme_sequence':
                await this.visemeManager.playVisemeSequence(payload.sequence || []);
                break;

            case 'start_lip_sync':
                if (payload.url) {
                    await this.lipSyncManager.startFromUrl(payload.url);
                }
                break;

            case 'stop_lip_sync':
                this.lipSyncManager.stop();
                break;

            case 'set_background':
                console.log('[Incarnation] Loading background:', payload.url);
                setBackground(payload.url);
                break;

            case 'focus_camera':
                console.log('[Incarnation] Focusing camera');
                if (this.model) {
                    focusOnHead(this.model);
                }
                break;

            default:
                console.warn('[Incarnation] Unknown command:', type);
        }
    }

    /**
     * Unlock audio/lip-sync context. 
     * Must be called from a user gesture.
     */
    async resumeAudio() {
        if (this.lipSyncManager) {
            await this.lipSyncManager.resume();
        }
    }

    // ── Per-frame update ────────────────────────────────────────────────────

    /** Call every frame with delta seconds. */
    update(delta) {
        if (this.animationManager) {
            this.animationManager.update(delta);
        }
        // Drive lip-sync visemes from audio analysis
        this.lipSyncManager.update();
        // VRM models need per-frame updates for spring bones, expressions, etc.
        if (this.vrm) {
            this.vrm.update(delta);
        }
    }

    // ── Private helpers ─────────────────────────────────────────────────────

    /**
     * Set expressions — uses VRM expressionManager if VRM, else raw morph targets.
     * @param {Record<string, number>} expressions
     */
    _setExpressions(expressions) {
        if (this.isVRM && this.vrm.expressionManager) {
            for (const [name, value] of Object.entries(expressions)) {
                this.vrm.expressionManager.setValue(name, Math.max(0, Math.min(1, value)));
            }
        } else {
            this.expressionManager.setExpressions(expressions);
        }
    }

    /** Clear all expressions. */
    _clearExpressions() {
        if (this.isVRM && this.vrm.expressionManager) {
            // Reset all VRM expression presets to 0
            const names = this._listVRMExpressions();
            for (const name of names) {
                this.vrm.expressionManager.setValue(name, 0);
            }
        } else {
            this.expressionManager.clearExpressions();
        }
    }

    /** @returns {string[]} Available VRM expression names. */
    _listVRMExpressions() {
        if (!this.vrm?.expressionManager) return [];
        // three-vrm stores expressions in a Map-like _expressionMap
        const mgr = this.vrm.expressionManager;
        const names = [];
        // Use the expressions getter which returns VRMExpression[]
        if (mgr.expressions) {
            for (const expr of mgr.expressions) {
                if (expr.expressionName) {
                    names.push(expr.expressionName);
                }
            }
        }
        return names.sort();
    }

    /**
     * Gather model info for reporting back to PlayAIdes.
     * @param {import('three').SkinnedMesh[]} skinnedMeshes
     */
    _getModelInfo(skinnedMeshes) {
        return {
            type: this.isVRM ? 'vrm' : 'gltf',
            animations: this.animationManager?.listClips() || [],
            morphTargets: listMorphTargets(skinnedMeshes),
            expressions: this.expressionManager.listExpressions(),
            visemes: this.visemeManager.listVisemes(),
            vrmExpressions: this._listVRMExpressions(),
        };
    }
}
