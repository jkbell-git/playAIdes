import { describe, it, expect } from 'vitest';
import { detectBackgroundType } from './sceneBackgrounds.js';

describe('detectBackgroundType', () => {
    it('returns "flat" for .jpg / .jpeg / .png / .webp', () => {
        expect(detectBackgroundType('foo.jpg')).toBe('flat');
        expect(detectBackgroundType('foo.JPEG')).toBe('flat');
        expect(detectBackgroundType('scene/castle.png')).toBe('flat');
        expect(detectBackgroundType('https://x.test/y.webp')).toBe('flat');
    });

    it('returns "hdri" for .hdr / .exr', () => {
        expect(detectBackgroundType('panorama.hdr')).toBe('hdri');
        expect(detectBackgroundType('PANORAMA.EXR')).toBe('hdri');
    });

    it('returns "glb" for .glb / .gltf', () => {
        expect(detectBackgroundType('scene.glb')).toBe('glb');
        expect(detectBackgroundType('scene/diorama.gltf')).toBe('glb');
    });

    it('returns "unknown" for unrecognized or empty input', () => {
        expect(detectBackgroundType('foo.txt')).toBe('unknown');
        expect(detectBackgroundType('')).toBe('unknown');
        expect(detectBackgroundType(null)).toBe('unknown');
        expect(detectBackgroundType(undefined)).toBe('unknown');
    });

    it('strips query strings and fragments before extension match', () => {
        expect(detectBackgroundType('foo.jpg?v=2')).toBe('flat');
        expect(detectBackgroundType('foo.glb#model')).toBe('glb');
    });
});
