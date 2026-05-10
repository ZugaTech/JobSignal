/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Empty = same origin as the SPA (e.g. FastAPI serves UI + API). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
