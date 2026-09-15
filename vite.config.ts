import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import zhihuTopics from './scripts/zhihu-topics-plugin.mjs'

export default defineConfig(({ mode }) => {
  const folioDevTarget = loadEnv(mode, '.', '').DEV_FOLIO_TARGET ?? 'http://127.0.0.1:5175'

  return {
    plugins: [react(), zhihuTopics()],
    server: {
      port: 5174,
      strictPort: true,
      hmr: { clientPort: 5174 },
      // Browser QA keeps a Chromium profile in the repo. Its locked cookie files
      // must never be watched by Vite on Windows or the dev server can exit.
      watch: { ignored: ['**/.workbuddy/**'] },
      proxy: {
        // Folio homepage world — browser only talks to 5174; Folio Vite stays internal.
        '/folio-home': {
          target: folioDevTarget,
          changeOrigin: true,
          ws: true,
        },
        '/ws': { target: 'http://127.0.0.1:8000', ws: true },
        '/tables': { target: 'http://127.0.0.1:8000' },
        '/demo': { target: 'http://127.0.0.1:8000' },
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
  }
})
