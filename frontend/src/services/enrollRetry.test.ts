import { afterEach, describe, expect, it, vi } from "vitest";
import { faceApi } from "./apiClient";

const success = () => Promise.resolve(new Response(JSON.stringify({ success: true, data: { face_profile_id: "p1" } })));
const rejected = (status: number, code: string) => Promise.resolve(new Response(
  JSON.stringify({ success: false, message: "no", error: { code } }), { status }));
const enroll = () => faceApi.enrollFace({ deviceCode: "KIOSK", imageBlob: new Blob(["x"]), fields: { full_name: "A" } });
const keyOf = (call: unknown[]) => ((call[1] as RequestInit).body as FormData).get("enrollment_id");

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("face enrollment retry", () => {
  it("resends the same image with the same enrollment_id when the response is lost", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("network down")).mockImplementationOnce(success);
    vi.stubGlobal("fetch", fetchMock);
    const result = enroll();
    await vi.runAllTimersAsync();
    expect(await result).toEqual({ face_profile_id: "p1" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(keyOf(fetchMock.mock.calls[0])).toMatch(/^[0-9a-f-]{36}$/);
    expect(keyOf(fetchMock.mock.calls[1])).toBe(keyOf(fetchMock.mock.calls[0]));
  });

  it("gives up after two attempts", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("network down"));
    vi.stubGlobal("fetch", fetchMock);
    const result = expect(enroll()).rejects.toThrow();
    await vi.runAllTimersAsync();
    await result;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never retries an answer from the backend", async () => {
    const fetchMock = vi.fn().mockImplementation(() => rejected(422, "MULTIPLE_FACES_DETECTED"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(enroll()).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses a new enrollment_id for each captured image", async () => {
    const fetchMock = vi.fn().mockImplementation(success);
    vi.stubGlobal("fetch", fetchMock);
    await enroll(); await enroll();
    expect(keyOf(fetchMock.mock.calls[0])).not.toBe(keyOf(fetchMock.mock.calls[1]));
  });
});
