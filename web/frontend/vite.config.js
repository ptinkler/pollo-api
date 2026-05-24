import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/',
  server: {
    proxy: {
      '/api': 'http://localhost:5000',
      '/video': 'http://localhost:5000',
      '/video-thumb': 'http://localhost:5000',
      '/image': 'http://localhost:5000',
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.js'],
  }
})

