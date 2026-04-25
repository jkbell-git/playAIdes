import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        include: ['src/**/*.test.js'],
        // Don't fail the Docker build target when no tests exist yet — the
        // first real tests land in Task 6 (viewerConfig) and Task 7 (viewerState).
        passWithNoTests: true,
    },
});
