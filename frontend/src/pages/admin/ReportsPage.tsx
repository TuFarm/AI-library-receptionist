import { useEffect, useState } from "react";
import { MetricCard, PageHeader } from "../../components/ui";
import { reportsApi, type ReportsOverview, type SessionReport } from "../../services/apiClient";

const PERIOD_OPTIONS = [7, 14, 30] as const;

export default function ReportsPage() {
  const [overview, setOverview] = useState<ReportsOverview | null>(null);
  const [sessions, setSessions] = useState<SessionReport | null>(null);
  const [days, setDays] = useState<number>(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    Promise.all([
      reportsApi.getOverview(days),
      reportsApi.getSessions(days),
    ]).then(([o, s]) => { if (current) { setOverview(o); setSessions(s); } })
      .catch((reason: Error) => { if (current) setError(reason.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [days, retry]);

  if (error) return <><PageHeader title="Báo cáo tổng quan" description="Không thể tải dữ liệu báo cáo."/>
    <section className="panel empty-state"><strong>Đã xảy ra lỗi</strong><p role="alert">{error}</p><button onClick={() => setRetry(value => value + 1)}>Thử lại</button></section></>;
  if (loading || !overview || !sessions) return <><PageHeader title="Báo cáo tổng quan" description="Đang tải dữ liệu báo cáo…"/><section className="panel loading-state">Đang tải báo cáo…</section></>;

  return <><PageHeader eyebrow="BÁO CÁO" title="Báo cáo tổng quan" description="Các chỉ số vận hành của kiosk từ dữ liệu thực tế." action={<div className="admin-report-actions">
    {PERIOD_OPTIONS.map(d => <button key={d} className={d === days ? "" : "secondary"} onClick={() => setDays(d)}>{d} ngày</button>)}
  </div>}/>
    <div className="metric-grid compact">
      <MetricCard icon="◫" label="Tổng phiên" value={overview.total_sessions.toLocaleString("vi-VN")} detail={`${overview.identified_users.toLocaleString("vi-VN")} người dùng đã nhận diện`}/>
      <MetricCard icon="?" label="Câu hỏi" value={overview.total_questions.toLocaleString("vi-VN")} detail={`${overview.total_ai_answers.toLocaleString("vi-VN")} câu trả lời AI`}/>
      <MetricCard icon="◎" label="Nhận diện" value={`${overview.recognition_success_rate}%`} detail={`${overview.recognition_success} thành công / ${overview.recognition_failure} thất bại`}/>
      <MetricCard icon="◷" label="Thời gian chờ" value={`${overview.avg_wait_seconds}s`} detail="Thời gian xử lý trung bình"/>
    </div>

    <div className="dashboard-grid">
      <section className="panel"><div className="panel-head"><h2>Phân bố theo lý do kết thúc</h2></div>
        {Object.keys(sessions.by_exit_reason).length === 0
          ? <div className="empty-state"><p>Chưa có dữ liệu phiên.</p></div>
          : <div className="data-table">{Object.entries(sessions.by_exit_reason).sort((a, b) => b[1] - a[1]).map(([reason, count]) =>
            <div className="table-row" key={reason}><strong>{reason}</strong><span>{count.toLocaleString("vi-VN")} phiên</span></div>
          )}</div>}
      </section>

      <section className="panel"><div className="panel-head"><h2>Phân bố theo thiết bị</h2></div>
        {Object.keys(sessions.by_device).length === 0
          ? <div className="empty-state"><p>Chưa có dữ liệu thiết bị.</p></div>
          : <div className="data-table">{Object.entries(sessions.by_device).sort((a, b) => b[1] - a[1]).map(([device, count]) =>
            <div className="table-row" key={device}><strong>{device === "unknown" ? "Không xác định" : device}</strong><span>{count.toLocaleString("vi-VN")} phiên</span></div>
          )}</div>}
      </section>
    </div>

    <section className="panel reports-average-panel"><div className="panel-head"><h2>Thời gian phiên trung bình</h2></div>
      <div className="metric-grid compact">
        <MetricCard icon="⏱" label="Trung bình" value={`${sessions.avg_duration_seconds}s`} detail="Thời lượng phiên trung bình"/>
        <MetricCard icon="!" label="Lỗi hạ tầng" value={overview.camera_network_errors.toLocaleString("vi-VN")} detail="Camera / Network errors"/>
      </div>
    </section>
  </>;
}
