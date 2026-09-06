import { app, BrowserWindow, ipcMain, session } from "electron";
import isDev from "electron-is-dev";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const devServerUrl = process.env.ELECTRON_RENDERER_URL ?? "http://localhost:5173";

// Electron currently reports camera/microphone requests as "media". The
// additional names retain compatibility with platform and Electron variations.
const kioskPermissions = new Set([
  "media",
  "camera",
  "microphone",
  "audioCapture",
  "videoCapture",
]);

function trusted(url) {
  if (isDev) { try { return new URL(url).origin === new URL(devServerUrl).origin; } catch { return false; } }
  return url.split("#")[0] === new URL("../dist/index.html", import.meta.url).href;
}
function configureKioskPermissions() {
  session.defaultSession.setPermissionRequestHandler(
    (contents, permission, callback, details) => callback(Boolean(contents && trusted(contents.getURL()) && trusted(details.requestingUrl) && kioskPermissions.has(permission))),
  );
  session.defaultSession.setPermissionCheckHandler((contents, permission, origin, details) => Boolean(contents && trusted(contents.getURL()) && kioskPermissions.has(permission) && (trusted(details.requestingUrl ?? origin) || origin === "file://")));
}

async function createWindow() {
  const window = new BrowserWindow({
    kiosk: true,
    fullscreen: true,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => { if (!trusted(url)) event.preventDefault(); });
  window.webContents.on("render-process-gone", () => { if (!window.isDestroyed()) window.reload(); });
  if (isDev) {
    await window.loadURL(devServerUrl);
  } else {
    await window.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

app.whenReady().then(async () => {
  configureKioskPermissions();
  ipcMain.handle("kiosk:get-app-version", (event) => { if (!trusted(event.senderFrame?.url ?? "")) throw new Error("Untrusted renderer"); return app.getVersion(); });
  ipcMain.handle("kiosk:get-diagnostics", (event) => {
    if (!trusted(event.senderFrame?.url ?? "")) throw new Error("Untrusted renderer");
    return { version: app.getVersion(), electron: process.versions.electron, processes: app.getAppMetrics().map(({ pid, type, cpu, memory }) => ({ pid, type, cpu, memory })) };
  });
  await createWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

