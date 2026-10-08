import type { Citation, KioskMessage } from "../../types/kiosk";

export function formatCitation(citation: Citation): string {
  const where = citation.page_number ? ` (tr. ${citation.page_number})` : citation.sheet_name ? ` (${citation.sheet_name})` : "";
  return `${citation.title}${where}`;
}

/** One chat turn; assistant answers grounded on knowledge documents list their sources. */
export default function ChatBubble({ message, icon }: { message: KioskMessage; icon: string }) {
  const sources = [...new Set((message.citations ?? []).map(formatCitation))];
  return <div className={`kiosk-bubble ${message.role}`}>
    <span>{message.role === "assistant" ? icon : "Bạn"}</span>
    <div><p>{message.text}</p>{sources.length > 0 && <small className="kiosk-sources">Nguồn: {sources.join(" · ")}</small>}</div>
  </div>;
}
