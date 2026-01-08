import { defineConfig } from 'vite';

export default defineConfig({
  root: './public',     // Her ligger din index.html
  build: {
    outDir: 'dist',     // Hvor Vite skal bygge til
    emptyOutDir: true
  }
});
