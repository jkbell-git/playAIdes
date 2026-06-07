import { describe, it, expect } from 'vitest';
import { stageLayoutFromMessage } from './stageLayout.js';

describe('stageLayoutFromMessage', () => {
    it('show_pip with a url and split enabled → split-camera', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam', kind: 'live' }, { splitEnabled: true });
        expect(v).toEqual({ layout: 'split-camera', feedUrl: 'http://x/cam', feedKind: 'live' });
    });

    it('defaults kind to snapshot', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam' }, { splitEnabled: true });
        expect(v.feedKind).toBe('snapshot');
    });

    it('split disabled → full (let the floating PiP handle it)', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam' }, { splitEnabled: false });
        expect(v).toEqual({ layout: 'full', feedUrl: '', feedKind: null });
    });

    it('show_pip with no url → full', () => {
        const v = stageLayoutFromMessage('show_pip', {}, { splitEnabled: true });
        expect(v.layout).toBe('full');
    });

    it('dismiss_pip → full', () => {
        const v = stageLayoutFromMessage('dismiss_pip', {}, { splitEnabled: true });
        expect(v).toEqual({ layout: 'full', feedUrl: '', feedKind: null });
    });

    it('unknown type → full', () => {
        expect(stageLayoutFromMessage('whatever', { url: 'x' }, { splitEnabled: true }).layout).toBe('full');
    });

    it('splitEnabled defaults to true when opts omitted', () => {
        expect(stageLayoutFromMessage('show_pip', { url: 'x' }).layout).toBe('split-camera');
    });
});
