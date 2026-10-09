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
