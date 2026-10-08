import { useEffect, useState } from "react";
import { PageHeader } from "../../components/ui";
import { adminApi } from "../../services/apiClient";

type ModuleStatus = { module: string; status: string; warning?: string | null };

export function statusTone(item: ModuleStatus): "success" | "warning" | "danger" {
  if (item.status === "mock") return "danger";
  return item.warning ? "warning" : "success";
}

export default function FeatureStatusPage() {
  const [modules, setModules] = useState<ModuleStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    void adminApi.getStatus().then(value => { if (current) setModules(value); })
      .catch((reason: Error) => { if (current) setError(reason.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [retry]);
  return <><PageHeader eyebrow="TRẠNG THÁI RUNTIME" title="Trạng thái tính năng" description="Theo dõi ranh giới giữa runtime thử nghiệm và tích hợp production."/>
    {loading ? <section className="panel loading-state">Đang tải trạng thái…</section> : error ? <section className="panel empty-state"><p role="alert">{error}</p><button onClick={() => setRetry(value => value + 1)}>Thử lại</button></section> : <section className="panel feature-list">{modules.map(item => <div className="status-row" key={item.module}>
      <div><strong>{item.module}</strong>{item.warning && <small>{item.warning}</small>}</div>
      <span className={`badge ${statusTone(item)}`}>{item.status}</span>
    </div>)}</section>}</>;
}
