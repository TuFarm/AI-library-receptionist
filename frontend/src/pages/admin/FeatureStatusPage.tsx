import { useEffect, useState } from "react";
import { PageHeader } from "../../components/ui";
import { adminApi } from "../../services/apiClient";

type ModuleStatus = { module: string; status: string; warning?: string | null };
const fallback: ModuleStatus[] = [
  { module: "Database", status: "Chưa xác định" },
  { module: "FaceID", status: "Chưa đọc được cấu hình", warning: "FACE_PROVIDER=mock chỉ dành cho kiểm thử và không nhận diện danh tính thật." },
];

export default function FeatureStatusPage() {
  const [modules, setModules] = useState<ModuleStatus[]>(fallback);
  useEffect(() => { void adminApi.getStatus().then(setModules).catch(() => undefined); }, []);
  return <><PageHeader eyebrow="TRẠNG THÁI RUNTIME" title="Trạng thái tính năng" description="Theo dõi ranh giới giữa runtime thử nghiệm và tích hợp production."/>
    <section className="panel feature-list">{modules.map(item => <div className="status-row" key={item.module}>
      <div><strong>{item.module}</strong>{item.warning && <small>{item.warning}</small>}</div>
      <span className={`badge ${item.status === "mock" ? "danger" : "warning"}`}>{item.status}</span>
    </div>)}</section></>;
}
