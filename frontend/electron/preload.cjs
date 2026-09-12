const { contextBridge, ipcRenderer } = require("electron");
const api = {
  getAppVersion: () => ipcRenderer.invoke("kiosk:get-app-version"),
};
contextBridge.exposeInMainWorld("kiosk", api);
