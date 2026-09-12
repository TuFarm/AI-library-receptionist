export type KioskIdleFact = { id: string; text: string };

export const KIOSK_IDLE_FACTS: readonly KioskIdleFact[] = [
  { id: "questions", text: "Bạn có thể hỏi kiosk về vị trí sách, giờ phục vụ và cách mượn trả." },
  { id: "discovery", text: "Kiosk có thể hỗ trợ tìm và gợi ý tài liệu theo chủ đề." },
  { id: "librarian", text: "Hãy liên hệ quầy thủ thư nếu bạn cần hỗ trợ trực tiếp." },
  { id: "study", text: "Hãy thử mô tả môn học hoặc chủ đề bạn quan tâm để nhận gợi ý phù hợp." },
  { id: "touch", text: "Chỉ cần chạm màn hình, trợ lý thư viện sẽ sẵn sàng hỗ trợ bạn." },
] as const;
