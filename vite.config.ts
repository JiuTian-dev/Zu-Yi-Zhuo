import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/ws': { target: 'http://127.0.0.1:8000', ws: true },
      '/tables': { target: 'http://127.0.0.1:8000' },
      '/matches': { target: 'http://127.0.0.1:8000' },
      '/participants': { target: 'http://127.0.0.1:8000' },
      '/personal-context': { target: 'http://127.0.0.1:8000' },
      '/opportunities': { target: 'http://127.0.0.1:8000' },
      '/intents': { target: 'http://127.0.0.1:8000' },
      '/healthz': { target: 'http://127.0.0.1:8000' },
      '/readyz': { target: 'http://127.0.0.1:8000' },
      '/capabilities': { target: 'http://127.0.0.1:8000' },
    },
  },
})
