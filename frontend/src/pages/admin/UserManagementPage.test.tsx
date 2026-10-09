import { describe, expect, it } from "vitest";
import { validateForm } from "./UserManagementPage";

const valid = { student_code: "TEST001", full_name: "Test User", email: "test@example.test",
  faculty: "", major: "", admission_year: "2024" };

describe("staff profile form validation", () => {
  it("accepts valid data and nullable fields when editing", () => {
    expect(validateForm(valid, false)).toEqual({});
    expect(validateForm({ ...valid, student_code: "", email: "", admission_year: "" }, true)).toEqual({});
  });

  it.each([
    ["full_name", " "], ["full_name", "x".repeat(256)], ["email", "invalid"],
    ["student_code", "AB C"],
    ["admission_year", "2024.5"], ["admission_year", String(new Date().getFullYear() + 2)],
    ["faculty", "x".repeat(151)], ["major", "x".repeat(151)],
  ])("rejects invalid %s", (field, value) => {
    expect(validateForm({ ...valid, [field]: value }, false)).toHaveProperty(field);
  });

  it("requires a student code and email on creation", () => {
    const errors = validateForm({ ...valid, student_code: "", email: "" }, false);
    expect(errors).toHaveProperty("student_code");
    expect(errors).toHaveProperty("email");
  });
});

describe("admin Face ID erasure form", () => {
  it("needs a reason and the student at the desk", async () => {
    const { canEraseFaceId } = await import("./UserManagementPage");
    expect(canEraseFaceId("SV mang thẻ đến quầy", true)).toBe(true);
    expect(canEraseFaceId("SV mang thẻ đến quầy", false)).toBe(false);
    expect(canEraseFaceId("  ab  ", true)).toBe(false);
    expect(canEraseFaceId("x".repeat(501), true)).toBe(false);
  });
});
