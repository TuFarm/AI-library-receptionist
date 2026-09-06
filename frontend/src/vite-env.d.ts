/// <reference types="vite/client" />

interface Window {
  kiosk?: { getAppVersion: () => Promise<string>; onPresence?: (listener: (present: boolean) => void) => () => void; getDiagnostics?: () => Promise<Record<string, unknown>> };
}
