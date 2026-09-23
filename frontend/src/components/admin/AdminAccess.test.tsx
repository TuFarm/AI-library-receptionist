import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminAccess from "./AdminAccess";
import { adminApi, adminUserApi, apiClient, reportsApi } from "../../services/apiClient";
import { adminHeaders, clearAdminSession, saveAdminSession, getAdminSession, adminDeviceId } from "../../services/adminAccess";

afterEach(() => { clearAdminSession(); vi.unstubAllGlobals(); });

describe("admin access", () => {
  it("hides staff pages behind a password input", () => {
    const html = renderToStaticMarkup(<AdminAccess><p>private staff data</p></AdminAccess>);
    expect(html).toContain("Xác thực quản trị");
    expect(html).toContain('type="password"');
    expect(html).not.toContain("private staff data");
  });

  it("verifies access without retaining a rejected credential", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: false, message: "Không có quyền truy cập quản trị.", error: { code: "ADMIN_ACCESS_DENIED" },
    }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(adminApi.verifyAccess("incorrect", "wrong")).rejects.toMatchObject({ status: 403, code: "ADMIN_ACCESS_DENIED" });
    expect(adminHeaders()).not.toHaveProperty("Authorization");
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ username: "incorrect", password: "wrong" }));
  });

  it("attaches staff credentials to admin requests and clears them on logout", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ success: true, data: {} }))));
    vi.stubGlobal("fetch", fetchMock);
    saveAdminSession({ username: "test-user", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 });
    await adminApi.getDashboard();
    await adminUserApi.list("Test User");
    await adminUserApi.update("test-id", { full_name: "Updated" });
    await adminUserApi.delete("test-id");
    await reportsApi.getOverview();
    for (const [, options] of fetchMock.mock.calls) expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(fetchMock.mock.calls[1][0]).toContain("search=Test%20User");
    await adminUserApi.list("", 20, 20);
    expect(fetchMock.mock.lastCall?.[0]).toContain("offset=20&limit=20");
    clearAdminSession();
    await adminApi.getStatus();
    expect(fetchMock.mock.lastCall?.[1].headers).not.toHaveProperty("Authorization");
  });

  it("does not attach staff credentials to ordinary kiosk requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: {} })));
    vi.stubGlobal("fetch", fetchMock);
    saveAdminSession({ username: "test-user", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 });
    await apiClient.get("/health");
    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });

  it("reports network failures without exposing the supplied key", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("test-staff-key")));
    await expect(adminApi.verifyAccess("test-user", "test-pass")).rejects.toThrow("Không thể kết nối máy chủ");
  });

  it("stores an expiring token and restores it without storing the password", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
    const session = { username: "test-user", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 };
    saveAdminSession(session);
    expect(getAdminSession()).toEqual(session);
    expect(JSON.stringify([...values.values()])).not.toContain("password");
    expect(adminDeviceId()).toBe(adminDeviceId());
    saveAdminSession({ ...session, expires_at: Math.floor(Date.now() / 1000) - 1 });
    expect(getAdminSession()).toBeNull();
    expect(adminHeaders()).not.toHaveProperty("Authorization");
  });

  it("sends the device header on login and translates validation errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: false, message: "Validation error",
      error: { code: "VALIDATION_ERROR", details: [{ loc: ["body", "username"], type: "missing" }] },
    }), { status: 422 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(adminApi.verifyAccess("", "test-pass")).rejects.toMatchObject({
      message: "Tên đăng nhập là bắt buộc.", fieldErrors: { username: "Tên đăng nhập là bắt buộc." },
    });
    expect(fetchMock.mock.calls[0][1].headers["X-Admin-Device"]).toBeTruthy();
  });

  it("clears an invalid server session", async () => {
    saveAdminSession({ username: "test-user", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: false, message: "Session expired" }), { status: 401 })));
    await expect(adminApi.getSession()).rejects.toMatchObject({ status: 401 });
    expect(getAdminSession()).toBeNull();
  });
});
