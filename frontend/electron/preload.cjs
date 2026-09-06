const { contextBridge, ipcRenderer } = require("electron");
const api = {
  getAppVersion: () => ipcRenderer.invoke("kiosk:get-app-version"),
  getDiagnostics: () => ipcRenderer.invoke("kiosk:get-diagnostics"),
};
// Enable only after wiring a physical presence sensor in the main process.
if (process.argv.includes("--kiosk-external-presence")) {
  api.onPresence = (listener) => {
    const handler = (_event, present) => { if (typeof present === "boolean") listener(present); };
    ipcRenderer.on("kiosk:presence", handler);
    return () => ipcRenderer.removeListener("kiosk:presence", handler);
  };
}
contextBridge.exposeInMainWorld("kiosk", api);
