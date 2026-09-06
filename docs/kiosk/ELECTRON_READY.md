# Electron readiness

The renderer uses an IPC-ready platform bridge and separate camera, voice, streaming and session adapters. Electron runs fullscreen/kiosk with contextIsolation enabled, nodeIntegration disabled and sandbox enabled. The sandbox preload is CommonJS (preload.cjs), exposing only narrow functions.

## Implemented checklist

- [x] Fullscreen kiosk window; packaged renderer uses existing MemoryRouter kiosk entry.
- [x] Camera ownership and teardown separate from UI.
- [x] WebSocket transport and centralized event bus separate from React screens.
- [x] Replaceable AssistantAvatar renderer contract (mood, label).
- [x] Camera and microphone permissions limited to the trusted renderer.
- [x] New windows denied and navigation away from the trusted renderer blocked.
- [x] IPC version/diagnostics calls validate the sending frame.
- [x] Actual Electron process CPU/memory diagnostics exposed through IPC.
- [x] Renderer crash reload handler.
- [x] Optional presence subscription with cleanup, without renderer Node access.

## Hardware integration contract

Only after installing a real sensor driver, add `--kiosk-external-presence` to `BrowserWindow` `webPreferences.additionalArguments`. Have the main process publish `window.webContents.send("kiosk:presence", boolean)` on sensor edges. The preload then exposes `onPresence(listener)`, returning an unsubscribe function. Without that hardware bridge the production idle screen stays asleep; developer mode provides an explicit presence simulation control. No physical sensor driver is fabricated by this change.

## Before permanent installation

- [ ] Package and test the Windows installer on the target Windows version; verify both camera and microphone permissions.
- [ ] Select/test a native or service-backed speech recognition adapter and a Vietnamese TTS voice. Browser development speech support does not establish Electron support.
- [ ] Install/test the local HOG/landmark/embedding dependencies with the actual camera. Calibrate quality and identity thresholds across representative users and lighting.
- [ ] Connect the real presence device and verify camera LED is off while idle and during conversation.
- [ ] Provision backend lifecycle, loopback binding, device authentication, service supervision, startup at login, sleep prevention, updates and rollback.
- [ ] Add CSP/custom protocol and test packaged origin handling; remove unneeded development origins.
- [ ] Run unplug/replug, network interruption, renderer crash, power-cycle and 24–72 hour memory/CPU soak tests.
- [ ] Resolve existing biometric template encryption, consent, retention, and anti-spoofing requirements before production face authentication.

Developer diagnostics require a development build and VITE_ENABLE_DEV_CONTROLS=true. Browsers show FPS, boxes/IDs, confidence and network/processing latency. CPU/memory are available only through Electron diagnostics; unsupported metrics are not invented. The runtime is Electron-ready architecture, not a verified production installer.
