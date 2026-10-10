/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "auto" (default): recorded data first, offer the API when found. "live" or "recorded" to force. */
  readonly VITE_SOURCE?: 'auto' | 'live' | 'recorded'
  /** Base URL of the StackTrace API. Default http://127.0.0.1:8000 */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
