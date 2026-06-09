import { describe, it, expect } from 'vitest';
import {
  groupByDomain, setSingleMapping, setPipCameraSource, setPipUrlSource, isResolved,
} from './mappingsModel.js';

describe('mappingsModel', () => {
  it('groups discovered items by domain', () => {
    const items = [
      { id: 'camera.a', domain: 'camera', name: 'A', capabilities: ['pip'] },
      { id: 'script.b', domain: 'script', name: 'B', capabilities: ['scripts'] },
    ];
    const groups = groupByDomain(items);
    expect(Object.keys(groups).sort()).toEqual(['camera', 'script']);
    expect(groups.camera[0].id).toBe('camera.a');
  });

  it('sets a single-entity capability mapping (e.g. say_target) immutably', () => {
    const before = { mappings: {} };
    const after = setSingleMapping(before, 'say_target', 'homeassistant', 'media_player.tv');
    expect(after.mappings.say_target).toEqual({ provider: 'homeassistant', entity: 'media_player.tv' });
    expect(before.mappings.say_target).toBeUndefined();
  });

  it('sets a typed pip CAMERA source immutably', () => {
    const before = { mappings: {} };
    const after = setPipCameraSource(before, 'homeassistant', 'camera.a');
    expect(after.mappings.pip).toEqual({ kind: 'camera', provider: 'homeassistant', entity: 'camera.a' });
    expect(before.mappings.pip).toBeUndefined();
  });

  it('sets a typed pip URL source immutably', () => {
    const after = setPipUrlSource({ mappings: {} }, 'https://grafana.local/d/abc', 'dashboard');
    expect(after.mappings.pip).toEqual({ kind: 'url', url: 'https://grafana.local/d/abc', label: 'dashboard' });
  });

  it('resolves a camera-kind pip against discovered ids; url-kind never goes stale', () => {
    const cam = { kind: 'camera', provider: 'homeassistant', entity: 'camera.a' };
    expect(isResolved(cam, ['camera.a', 'camera.b'])).toBe(true);
    expect(isResolved(cam, ['camera.b'])).toBe(false);
    expect(isResolved({ kind: 'url', url: 'https://x' }, [])).toBe(true);
    expect(isResolved({ provider: 'homeassistant', entity: 'media_player.tv' }, ['media_player.tv'])).toBe(true);
  });
});
