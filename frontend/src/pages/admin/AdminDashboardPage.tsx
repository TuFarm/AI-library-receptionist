import { useEffect, useMemo, useState } from "react";
import { MetricCard, PageHeader } from "../../components/ui";
import { adminApi, type AdminDashboard } from "../../services/apiClient";

const PERIOD_OPTIONS = [7, 14, 30] as const;

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState("");
  const [days, setDays] = useState<number>(7);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let current = true;
    setData(null);
    setError("");
    void adminApi.getDashboard(days).then(value => { if (current) setData(value); })
      .catch((reason: Error) => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [days, retry]);

  const maxSessions = useMemo(() => Math.max(...(data?.daily.map(item => item.sessions) ?? [1]), 1), [data]);

  if (error) return <><PageHeader title="Tổng quan hệ thống" description="Không thể tải dữ liệu vận hành."/><section className="panel empty-state"><strong>Đã xảy ra lỗi</strong><p role="alert">{error}</p><button onClick={() => setRetry(value => value + 1)}>Thử lại</button></section></>;
  if (!data) return <><PageHeader title="Tổng quan hệ thống" description="Đang tải dữ liệu vận hành…"/><section className="panel loading-state">Đang tải thống kê…</section></>;

  return <><PageHeader eyebrow="TỔNG QUAN HỆ THỐNG" title="Hoạt động thư viện" description="Số liệu được tổng hợp từ các phiên Kiosk và log vận hành thực tế." action={<div className="admin-report-actions">
    {PERIOD_OPTIONS.map(d => <button key={d} className={d === days ? "" : "secondary"} onClick={() => setDays(d)}>{d} ngày</button>)}
    <button className="admin-export-button" onClick={() => window.print()}>Xuất báo cáo</button>
  </div>}/>
    <div className="metric-grid">
      <MetricCard icon="◫" label="Lượt kiosk" value={data.total_sessions.toLocaleString("vi-VN")} detail="Tổng số phiên"/>
      <MetricCard icon="◎" label="Nhận diện thành công" value={data.recognition_success_count.toLocaleString("vi-VN")} detail={`${data.recognition_success_rate}% lượt thử thành công`}/>
      <MetricCard icon="×" label="Nhận diện thất bại" value={data.recognition_failure_count.toLocaleString("vi-VN")} detail="Lượt thử không xác định được"/>
      <MetricCard icon="?" label="Câu hỏi" value={data.questions.toLocaleString("vi-VN")} detail={`${data.ai_answers.toLocaleString("vi-VN")} câu trả lời AI`}/>
      <MetricCard icon="✓" label="Khảo sát" value={data.surveys.toLocaleString("vi-VN")} detail="Phản hồi đã gửi"/>
      <MetricCard icon="◷" label="Thời gian chờ nhận diện" value={`${data.avg_wait_seconds}s`} detail="Thời gian xử lý trung bình"/>
      <MetricCard icon="★" label="Mức hài lòng" value={data.avg_satisfaction != null ? `${data.avg_satisfaction.toLocaleString("vi-VN")} / 5` : "—"} detail="Trung bình điểm khảo sát"/>
      <MetricCard icon="▤" label="Trả lời có nguồn" value={`${data.grounded_rate}%`} detail={`${data.grounded_answers.toLocaleString("vi-VN")} câu trả lời dựa trên tài liệu`}/>
      <MetricCard icon="!" label="Lỗi camera/network" value={data.camera_network_errors.toLocaleString("vi-VN")} detail="Sự kiện lỗi hạ tầng"/>
    </div>
    <section className="panel"><div className="panel-head"><h2>Hoạt động {days} ngày gần nhất</h2><span className="badge success">Dữ liệu thật</span></div>
      {data.daily.length === 0 ? <div className="empty-state"><strong>Chưa có dữ liệu</strong><p>Chưa ghi nhận phiên kiosk nào trong hệ thống.</p></div> : <div className="bar-chart">{data.daily.map(item => <div key={item.date}><i style={{ height: `${Math.max(item.sessions / maxSessions * 100, 4)}%` }} title={`${item.sessions} phiên`}/><span>{new Date(item.date).toLocaleDateString("vi-VN", { weekday: "short" })}</span></div>)}</div>}
    </section>
  </>;
}
