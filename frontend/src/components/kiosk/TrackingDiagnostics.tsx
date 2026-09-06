import { useEffect, useState } from "react";
import { kioskEvents } from "../../runtime/eventBus";
type Face = { track_id: number; box: number[]; landmarks: number[][]; quality_ok: boolean };
export function TrackingDiagnostics({ developer = false }: { developer?: boolean }) {
  const [faces, setFaces] = useState<Face[]>([]);
  const [size, setSize] = useState<number[]>([640, 360]);
  const [confidence, setConfidence] = useState<Record<number, number>>({});
  useEffect(() => kioskEvents.subscribe(({ event, payload }) => {
    if (event === "face_tracking") { setFaces(payload.faces as Face[]); setSize(payload.frame_size as number[]); }
    if (event === "recognition_progress" && typeof payload.confidence === "number") {
      setConfidence(values => ({ ...values, [Number(payload.track_id)]: payload.confidence as number }));
    }
    if (event === "track_lost") setConfidence(values => {
      const next = { ...values }; delete next[Number(payload.track_id)]; return next;
    });
    if (event === "camera_stopped") { setFaces([]); setConfidence({}); }
  }), []);
  return <svg className={`tracking-diagnostics ${developer ? "developer" : "production"}`} preserveAspectRatio="xMidYMid meet" viewBox={`0 0 ${size[0]} ${size[1]}`} aria-label="Face tracking overlay">
    {faces.map(face => {
      const [top, right, bottom, left] = face.box;
      const score = confidence[face.track_id];
      const circleX = size[0] - left + 25;
      const circleY = top + 25;
      return <g className={`tracking-face ${face.quality_ok ? "good" : "waiting"}`} key={face.track_id} fill="none">
        <rect className="tracking-box" x={size[0]-right} y={top} width={right-left} height={bottom-top}/>
        <rect className="tracking-pulse" x={size[0]-right-7} y={top-7} width={right-left+14} height={bottom-top+14}/>
        {developer && <>
          {face.landmarks?.map(([x, y], index) => <circle className="tracking-landmark" key={index} cx={size[0]-x} cy={y} r="2.2"/>)}
          <circle className="confidence-base" cx={circleX} cy={circleY} r="19"/>
          <circle className="confidence-progress" cx={circleX} cy={circleY} r="19" pathLength="100" strokeDasharray={`${Math.round((score ?? 0)*100)} 100`}/>
          <text x={size[0]-right} y={Math.max(22, top-10)}>Track #{face.track_id}</text>
          <text x={circleX} y={circleY+5} textAnchor="middle">{score === undefined ? "--" : `${Math.round(score*100)}%`}</text>
        </>}
      </g>;
    })}
  </svg>;
}
