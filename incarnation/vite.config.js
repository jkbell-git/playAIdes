import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Multi-page app: one entry per surface. Viewer/creator pages stay vanilla
// (perf-critical, Fire TV); the console is a React page. Without this explicit
// rollupOptions.input, `vite build` would only emit index.html.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        creator: resolve(__dirname, 'creator.html'),
        'design-preview': resolve(__dirname, 'design-preview.html'),
        console: resolve(__dirname, 'console.html'),
      },
    },
  },
});
