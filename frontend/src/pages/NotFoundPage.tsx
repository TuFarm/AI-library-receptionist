import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return <section className="development-card"><div className="development-icon">?</div><h2>Không tìm thấy trang</h2>
    <p>Đường dẫn bạn vừa mở không tồn tại hoặc đã được di chuyển.</p>
    <Link className="button secondary" to="/">← Về trang chủ</Link></section>;
}
