/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backend = process.env.VITE_BACKEND ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Same-origin in dev: the browser only talks to Vite, which forwards API/admin to Django,
  // so session + CSRF cookies work exactly as behind Nginx in production.
  server: {
    port: 5173,
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
    },
  },
  test: { environment: 'jsdom' },
})
