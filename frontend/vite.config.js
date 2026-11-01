import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
    // The preview service supplies its own private hostname.
    allowedHosts: process.env.SITES_PREVIEW_ALLOWED_HOST ? [process.env.SITES_PREVIEW_ALLOWED_HOST] : undefined,
  },
  build: { outDir: 'dist' },
});
