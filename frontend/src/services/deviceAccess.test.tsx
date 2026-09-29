import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import KioskDeviceGate from "../components/kiosk/KioskDeviceGate";
import { apiClient, faceApi, kioskApi, userApi } from "./apiClient";
import { clearDeviceKey, DEVICE_UNAUTHORIZED_EVENT, getDeviceKey, isDeviceKey, saveDeviceKey } from "./deviceAccess";
import { validateDeviceForm } from "../pages/admin/DevicesPage";
import { validateStaffForm } from "../pages/admin/StaffAccountsPage";

const KEY = "kd_" + "a".repeat(43);
const ok = () => Promise.resolve(new Response(JSON.stringify({ success: true, data: {} })));

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});
afterEach(() => { clearDeviceKey(); vi.unstubAllGlobals(); });

describe("kiosk device key", () => {
  it("recognises only well-formed keys and persists them on the device", () => {
    expect(isDeviceKey(KEY)).toBe(true);
    expect(isDeviceKey("kd_short")).toBe(false);
    expect(isDeviceKey("Bearer abc")).toBe(false);
    saveDeviceKey(` ${KEY} `);
    expect(getDeviceKey()).toBe(KEY);
    clearDeviceKey();
    expect(getDeviceKey()).toBe("");
  });

  it("sends the key on kiosk requests, including multipart uploads", async () => {
    const fetchMock = vi.fn().mockImplementation(ok);
    vi.stubGlobal("fetch", fetchMock);
    saveDeviceKey(KEY);
    await apiClient.get("/surveys/active");
    await faceApi.enrollFace({ deviceCode: "KIOSK", imageBlob: new Blob(["x"]), fields: { full_name: "A" } });
    for (const [, options] of fetchMock.mock.calls) expect(options.headers["X-Device-Key"]).toBe(KEY);
    expect(fetchMock.mock.calls[1][1].body).toBeInstanceOf(FormData);
  });

  it("scopes kiosk profile edits to the live session, not a user id", async () => {
    const fetchMock = vi.fn().mockImplementation(ok);
    vi.stubGlobal("fetch", fetchMock);
    await userApi.update("session-1", { full_name: "Người A", major: "CNTT" });
    await userApi.deleteFaceId("session-1");
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/kiosk\/sessions\/session-1\/profile$/);
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/kiosk\/sessions\/session-1\/face-profile$/);
  });

  it("verifies a candidate key without saving it first", async () => {
    const fetchMock = vi.fn().mockImplementation(ok);
    vi.stubGlobal("fetch", fetchMock);
    await kioskApi.verifyDevice(KEY);
    expect(fetchMock.mock.calls[0][1].headers["X-Device-Key"]).toBe(KEY);
    expect(getDeviceKey()).toBe("");
  });

  it("announces a rejected key so the kiosk returns to device setup", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: false, message: "Khóa thiết bị không hợp lệ.", error: { code: "DEVICE_KEY_INVALID" },
    }), { status: 401 })));
    const target = new EventTarget();
    vi.stubGlobal("window", target);
    const listener = vi.fn();
    target.addEventListener(DEVICE_UNAUTHORIZED_EVENT, listener);
    await expect(apiClient.post("/kiosk/sessions/start", {})).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail.code).toBe("DEVICE_KEY_INVALID");
  });

  it("shows device setup instead of the kiosk until a key is present", () => {
    const setup = renderToStaticMarkup(<KioskDeviceGate><p>kiosk content</p></KioskDeviceGate>);
    expect(setup).toContain("Kết nối kiosk với hệ thống");
    expect(setup).not.toContain("kiosk content");
    saveDeviceKey(KEY);
    expect(renderToStaticMarkup(<KioskDeviceGate><p>kiosk content</p></KioskDeviceGate>)).toContain("kiosk content");
  });
});

describe("admin access forms", () => {
  it("validates staff accounts like the backend", () => {
    expect(validateStaffForm({ username: "thu.thu", full_name: "Thủ thư", role: "librarian", password: "12345678" })).toEqual({});
    expect(Object.keys(validateStaffForm({ username: "a b", full_name: " ", role: "admin", password: "short" })).sort())
      .toEqual(["full_name", "password", "username"]);
  });

  it("validates device registration", () => {
    expect(validateDeviceForm({ device_code: "KIOSK_TANG1", device_name: "Tầng 1", location: "" })).toEqual({});
    expect(Object.keys(validateDeviceForm({ device_code: "có dấu", device_name: "", location: "" })).sort())
      .toEqual(["device_code", "device_name"]);
  });
});
