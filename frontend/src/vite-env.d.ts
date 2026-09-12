/// <reference types="vite/client" />

interface Window {
  kiosk?: { getAppVersion: () => Promise<string> };
}
