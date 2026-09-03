interface ImportMetaEnv {
  readonly DEV: boolean
  readonly VITE_ALLOW_DEV_SEED?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_BASE_URL?: string
  readonly VITE_DAY_CYCLE_PROGRESS?: string
  readonly VITE_YEAR_CYCLE_PROGRESS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
