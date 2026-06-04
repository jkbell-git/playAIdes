// incarnation/src/pipOverlay.test.js
import { describe, it, expect } from 'vitest';
import { pipViewFromMessage } from './pipOverlay.js';

describe('pipViewFromMessage', () => {
    it('show_pip live → visible live view with url', () => {
        expect(pipViewFromMessage('show_pip', { url: 'http://x/stream', kind: 'live' }))
            .toEqual({ visible: true, url: 'http://x/stream', kind: 'live' });
    });

    it('show_pip defaults kind to snapshot', () => {
        expect(pipViewFromMessage('show_pip', { url: 'http://x.jpg' }))
            .toEqual({ visible: true, url: 'http://x.jpg', kind: 'snapshot' });
    });

    it('dismiss_pip → hidden', () => {
        expect(pipViewFromMessage('dismiss_pip', {}))
            .toEqual({ visible: false, url: '', kind: null });
    });

    it('show_pip with no url → hidden (nothing to show)', () => {
        expect(pipViewFromMessage('show_pip', {}))
            .toEqual({ visible: false, url: '', kind: null });
    });
});
