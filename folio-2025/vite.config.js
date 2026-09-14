import 'dotenv/config'
import restart from 'vite-plugin-restart'
import wasm from 'vite-plugin-wasm'
import topLevelAwait from 'vite-plugin-top-level-await'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { nodePolyfills } from 'vite-plugin-node-polyfills'

const parentPort = process.env.DEV_FRONTEND_PORT ?? '5174'
const folioPort = process.env.DEV_FOLIO_PORT ?? '5175'

export default {
    root: 'sources/', // Sources files (typically where index.html is)
    envDir: '../',  // Directory where the env file is located
    publicDir: '../static/', // Path from "root" to static assets (files that are served as they are)
    // Served under the parent app on :5174 via /folio-home proxy.
    base: '/folio-home/',
    server:
    {
        // https: true,
        host: '127.0.0.1',
        port: Number(folioPort),
        strictPort: true,
        open: false, // Opened by the parent 组一桌 app instead
        // HMR through the parent 5174 proxy so the browser only uses one port.
        origin: `http://127.0.0.1:${parentPort}`,
        hmr: {
            protocol: 'ws',
            host: '127.0.0.1',
            clientPort: Number(parentPort),
            path: '/folio-home/',
        },
    },
    build:
    {
        outDir: '../dist', // Output in the dist/ folder
        emptyOutDir: true, // Empty the folder first
        sourcemap: false // Add sourcemap
    },
    plugins:
    [
        wasm(),
        topLevelAwait(),
        restart({ restart: [ '../static/**', ] }), // Restart server on static file change
        nodePolyfills(),
        // basicSsl()
    ]
}
