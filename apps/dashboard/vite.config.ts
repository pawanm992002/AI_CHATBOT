import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/dashboard/',
  server: {
    port: 3000,
    proxy: {
      '^/(tenants|admin|chat|static|ws|widget|leads|feedback|dashboard/(sources|crawl|knowledge|docs|leads))': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
