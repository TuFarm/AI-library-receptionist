import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConversationLogsPage, { groundedLabel } from "./ConversationLogsPage";
import SurveyManagementPage, { validateSurvey } from "./SurveyManagementPage";
import { statusTone } from "./FeatureStatusPage";
import { answersToSubmit } from "../kiosk/KioskSurveyScreen";
import { conversationAdminApi, reportsApi, surveyAdminApi } from "../../services/apiClient";
import { clearAdminSession, saveAdminSession } from "../../services/adminAccess";

afterEach(() => { clearAdminSession(); vi.unstubAllGlobals(); });

const validSurvey = { survey_name: "Khảo sát kiosk", description: "", questions: [{ question_text: "Bạn hài lòng không?", question_type: "rating" as const }] };

describe("survey form validation", () => {
  it("accepts a valid survey", () => { expect(validateSurvey(validSurvey)).toEqual({}); });
  it("rejects short names, long descriptions and bad questions", () => {
    const errors = validateSurvey({ survey_name: "ab", description: "x".repeat(1001), questions: [{ question_text: "?", question_type: "text" }] });
    expect(Object.keys(errors).sort()).toEqual(["description", "question_0", "survey_name"]);
    expect(validateSurvey({ ...validSurvey, questions: [] })).toHaveProperty("questions");
    expect(validateSurvey({ ...validSurvey, questions: Array(21).fill(validSurvey.questions[0]) })).toHaveProperty("questions");
  });
  it("skips question checks when questions are locked by responses", () => {
    expect(validateSurvey({ ...validSurvey, questions: [] }, false)).toEqual({});
  });
});

describe("kiosk survey answers", () => {
  it("drops blank free-text answers but keeps ratings and choices", () => {
    expect(answersToSubmit({ a: 5, b: "Có", c: "   ", d: "Tốt" })).toEqual({ a: 5, b: "Có", d: "Tốt" });
  });
});

describe("labels", () => {
  it("summarises grounded answers", () => {
    expect(groundedLabel({ answer_count: 0, grounded_count: 0 })).toEqual(["Chưa có trả lời", "warning"]);
    expect(groundedLabel({ answer_count: 2, grounded_count: 2 })).toEqual(["Có nguồn", "success"]);
    expect(groundedLabel({ answer_count: 3, grounded_count: 1 })).toEqual(["2/3 không có nguồn", "danger"]);
  });
  it("colours feature status by mock/warning", () => {
    expect(statusTone({ module: "AI", status: "mock" })).toBe("danger");
    expect(statusTone({ module: "RAG", status: "0 tài liệu", warning: "Chưa có" })).toBe("warning");
    expect(statusTone({ module: "Database", status: "Completed" })).toBe("success");
  });
});

describe("pages render loading states", () => {
  it("conversation and survey pages", () => {
    expect(renderToStaticMarkup(<ConversationLogsPage/>)).toContain("Đang tải hội thoại…");
    const surveys = renderToStaticMarkup(<SurveyManagementPage/>);
    expect(surveys).toContain("Tạo khảo sát");
    expect(surveys).toContain("Chấm điểm 1–5 sao");
  });
});

describe("admin API clients", () => {
  it("build filtered URLs and send staff credentials", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ success: true, data: { items: [], metrics: [] } }))));
    vi.stubGlobal("fetch", fetchMock);
    saveAdminSession({ username: "librarian", token: "test-token", expires_at: Math.floor(Date.now() / 1000) + 900 });
    await conversationAdminApi.list({ days: 30, search: " wifi ", ungrounded: true, offset: 20 });
    expect(fetchMock.mock.lastCall?.[0]).toMatch(/\/admin\/conversations\?days=30&offset=20&limit=20&search=wifi&ungrounded=true$/);
    await surveyAdminApi.setActive("s1", false);
    expect(fetchMock.mock.lastCall?.[0]).toMatch(/\/admin\/surveys\/s1\/deactivate$/);
    await reportsApi.rebuildDaily(14);
    expect(fetchMock.mock.lastCall?.[0]).toMatch(/\/reports\/daily\/rebuild\?days=14$/);
    await reportsApi.getDaily(7);
    expect(fetchMock.mock.lastCall?.[0]).toMatch(/\/reports\/daily\?start_date=\d{4}-\d{2}-\d{2}&end_date=\d{4}-\d{2}-\d{2}$/);
    for (const [, options] of fetchMock.mock.calls) expect(options.headers.Authorization).toBe("Bearer test-token");
  });
});
