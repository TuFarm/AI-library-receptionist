import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import KnowledgePage, { formatSize, validateUpload } from "./KnowledgePage";
import ChatBubble, { formatCitation } from "../../components/kiosk/ChatBubble";
import { knowledgeApi } from "../../services/apiClient";
import { clearAdminSession, saveAdminSession } from "../../services/adminAccess";

afterEach(() => { clearAdminSession(); vi.unstubAllGlobals(); });

describe("knowledge upload validation", () => {
  it("accepts supported documents within the size limit", () => {
    for (const name of ["noi-quy.PDF", "a.docx", "b.xlsx", "c.txt", "d.md", "e.csv"]) expect(validateUpload({ name, size: 10 })).toBe("");
  });
  it.each([
    [null, "chọn tệp"], [{ name: "virus.exe", size: 10 }, "Chỉ hỗ trợ"], [{ name: "README", size: 10 }, "Chỉ hỗ trợ"],
    [{ name: "empty.txt", size: 0 }, "rỗng"], [{ name: "big.pdf", size: 3 * 1024 * 1024 }, "vượt quá 2 MB"],
  ])("rejects %j", (file, message) => { expect(validateUpload(file, 2)).toContain(message); });
  it("formats sizes", () => {
    expect(formatSize(null)).toBe("—"); expect(formatSize(512)).toBe("512 B"); expect(formatSize(2048)).toBe("2.0 KB"); expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("knowledge page and API", () => {
  it("renders upload, text, retrieval and loading states", () => {
    const html = renderToStaticMarkup(<KnowledgePage/>);
    expect(html).toContain("Tải lên và xử lý");
    expect(html).toContain('accept=".pdf,.docx,.xlsx,.txt,.md,.csv"');
    expect(html).toContain("Thử truy xuất");
    expect(html).toContain("Đang tải tài liệu…");
  });

  it("sends staff credentials, multipart uploads and JSON edits", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ success: true, data: { items: [] } }))));
    vi.stubGlobal("fetch", fetchMock);
    saveAdminSession({ username: "librarian", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 });
    await knowledgeApi.upload(new File(["Giờ mở cửa"], "gio.txt", { type: "text/plain" }), "  Giờ mở cửa ");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/knowledge\/documents$/);
    expect(options.body).toBeInstanceOf(FormData);
    expect((options.body as FormData).get("title")).toBe("Giờ mở cửa");
    expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(options.headers).not.toHaveProperty("Content-Type");  // browser sets the multipart boundary
    await knowledgeApi.update("doc-1", { is_active: false });
    expect(fetchMock.mock.lastCall?.[1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ is_active: false }) });
    await knowledgeApi.list("nội quy");
    expect(fetchMock.mock.lastCall?.[0]).toContain("search=n%E1%BB%99i%20quy");
  });
});

describe("kiosk citations", () => {
  const citation = { index: 1, chunk_id: "c", document_id: "d", title: "Nội quy", page_number: 3, sheet_name: null };
  it("shows deduplicated sources under grounded answers only", () => {
    expect(formatCitation(citation)).toBe("Nội quy (tr. 3)");
    expect(formatCitation({ ...citation, page_number: null, sheet_name: "Lịch" })).toBe("Nội quy (Lịch)");
    const grounded = renderToStaticMarkup(<ChatBubble icon="✦" message={{ id: "1", role: "assistant", text: "Có.", citations: [citation, { ...citation, index: 2 }] }}/>);
    expect(grounded).toContain("Nguồn: Nội quy (tr. 3)</small>");
    const plain = renderToStaticMarkup(<ChatBubble icon="✦" message={{ id: "2", role: "assistant", text: "Xin chào" }}/>);
    expect(plain).not.toContain("Nguồn");
  });
});
