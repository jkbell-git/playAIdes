import { describe, it, expect } from 'vitest';
import { SHOTS, chooseShot, computeShotPose } from './cameraDirector.js';

describe('chooseShot', () => {
    it('returns "full" while a one-shot animation is playing', () => {
        expect(chooseShot({ animating: true })).toBe('full');
    });

    it('returns "bust" when idle (no animation)', () => {
        expect(chooseShot({ animating: false })).toBe('bust');
        expect(chooseShot({})).toBe('bust');           // default
        expect(chooseShot()).toBe('bust');             // no args
    });
});

describe('computeShotPose', () => {
    // 2 m avatar standing at the origin; look at mid-height; frame the whole
    // 2 m; 45° vertical FOV → distance = (2 * 1 / 2) / tan(22.5°) = 2.4142.
    const box = { minY: 0, maxY: 2, cx: 0, cz: 0 };

    it('places the camera in front, level with and pointed at the look-at', () => {
        const pose = computeShotPose(box, { targetFrac: 0.5, extentFrac: 1.0 }, 45);
        expect(pose.target).toEqual({ x: 0, y: 1, z: 0 });
        expect(pose.position.x).toBe(0);
        expect(pose.position.y).toBe(1);                 // camera level with target
        expect(pose.position.z).toBeCloseTo(2.4142, 3);  // distance for a 2m extent @45°
    });

    it('a narrower FOV needs a greater distance to frame the same extent', () => {
        const wide = computeShotPose(box, { targetFrac: 0.5, extentFrac: 1.0 }, 60);
        const narrow = computeShotPose(box, { targetFrac: 0.5, extentFrac: 1.0 }, 30);
        expect(narrow.position.z).toBeGreaterThan(wide.position.z);
    });

    it('carries the avatar x/z through to both camera and target', () => {
        const offset = { minY: 0, maxY: 2, cx: 1.5, cz: -3 };
        const pose = computeShotPose(offset, { targetFrac: 0.5, extentFrac: 1.0 }, 45);
        expect(pose.target.x).toBe(1.5);
        expect(pose.target.z).toBe(-3);
        expect(pose.position.x).toBe(1.5);
        expect(pose.position.z).toBeGreaterThan(-3);     // camera sits in front (+z)
    });
});

describe('SHOTS presets', () => {
    it('bust frames the upper body and sits closer than full', () => {
        const box = { minY: 0, maxY: 1.6, cx: 0, cz: 0 };
        const bust = computeShotPose(box, SHOTS.bust, 45);
        const full = computeShotPose(box, SHOTS.full, 45);
        expect(bust.target.y).toBeGreaterThan(full.target.y);    // bust looks higher up
        expect(full.position.z).toBeGreaterThan(bust.position.z); // full pulls back farther
    });

    it('the bust shot keeps the head in frame (with headroom)', () => {
        const box = { minY: 0, maxY: 2, cx: 0, cz: 0 };
        const height = box.maxY - box.minY;
        const topOfFrame = box.minY + height * SHOTS.bust.targetFrac
            + (height * SHOTS.bust.extentFrac) / 2;
        expect(topOfFrame).toBeGreaterThanOrEqual(box.maxY);     // head not cropped
    });
});
