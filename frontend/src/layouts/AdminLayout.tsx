import { NavLink, Outlet } from "react-router-dom";
import { useState, type ReactNode } from "react";
import AdminAccess from "../components/admin/AdminAccess";
import AdminAccountMenu from "../components/admin/AdminAccountMenu";
export default function AdminLayout() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try { return localStorage.getItem("nlu.admin.theme") === "dark" ? "dark" : "light"; } catch { return "light"; }
  });
  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    try { localStorage.setItem("nlu.admin.theme", next); } catch { /* Theme still works for this page. */ }
  }
  return <div className="admin-theme" data-theme={theme}><AdminAccess>{signOut => <AdminShell onSignOut={signOut} theme={theme} onToggleTheme={toggleTheme}/>}</AdminAccess></div>;
}
function ProfileIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: "middle" }}>
    <circle cx="12" cy="8" r="4"/>
    <path d="M4 21v-2a8 8 0 0 1 16 0v2"/>
  </svg>;
}
const nav: [string, ReactNode, string][] = [["/admin/dashboard","⌂","Tổng quan"],["/admin/knowledge","▤","Tài liệu tri thức"],["/admin/conversations","☵","Hội thoại"],["/admin/users",<ProfileIcon/>,"Người dùng"],["/admin/surveys","✓","Khảo sát"],["/admin/reports","↗","Báo cáo"],["/admin/status","●","Trạng thái"]];
function AdminShell({ onSignOut, theme, onToggleTheme }: { onSignOut: () => Promise<void>; theme: "light" | "dark"; onToggleTheme: () => void }){return <div className="app-shell admin-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">NL</span><div><strong>NLU Library</strong><small>Admin Web</small></div></div><nav>{nav.map(([to,icon,label])=><NavLink key={to} to={to}><span className="nav-icon">{icon}</span><span>{label}</span></NavLink>)}</nav><div className="sidebar-foot"><span className="online-dot"/> Khu vực quản trị<small>Trang dành cho nhân viên</small></div></aside><section className="content-area"><header className="topbar"><div><span className="eyebrow">TRUNG TÂM QUẢN TRỊ</span><strong>Đại học Nông Lâm TP.HCM</strong></div><div className="top-actions"><button type="button" className="secondary admin-theme-toggle" onClick={onToggleTheme} aria-label={theme === "light" ? "Chuyển sang chế độ tối" : "Chuyển sang chế độ sáng"} aria-pressed={theme === "dark"}><span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>{theme === "light" ? "Chế độ tối" : "Chế độ sáng"}</button><AdminAccountMenu onSignOut={onSignOut}/></div></header><main className="page"><Outlet/></main></section></div>}
