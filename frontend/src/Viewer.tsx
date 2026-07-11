import { useCallback, useEffect, useRef, useState } from "react";

const API =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";

type Plane = "axial" | "coronal" | "sagittal";
type Meta = {
  id: string;
  shape: [number, number, number];
  spacing: [number, number, number];
  orientation: string;
  window_center: number;
  window_width: number;
};
type Volume = { data: Int16Array; dims: [number, number, number] };
type Annotation = { id: string; plane: Plane; slice_index: number; points: number[][]; label: string | null };

// index into the C-ordered [I,J,K] volume
const idx = (i: number, j: number, k: number, J: number, K: number) => i * (J * K) + j * K + k;

function planeSize(dims: [number, number, number], plane: Plane): [number, number] {
  const [I, J, K] = dims;
  if (plane === "axial") return [I, J]; // fix k
  if (plane === "coronal") return [I, K]; // fix j
  return [J, K]; // sagittal: fix i
}

function sampleValue(vol: Volume, plane: Plane, sliceIdx: number, x: number, y: number): number {
  const [, J, K] = vol.dims;
  if (plane === "axial") return vol.data[idx(x, y, sliceIdx, J, K)];
  if (plane === "coronal") return vol.data[idx(x, sliceIdx, y, J, K)];
  return vol.data[idx(sliceIdx, x, y, J, K)];
}

export default function Viewer() {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [center, setCenter] = useState(40);
  const [width, setWidth] = useState(400);
  const [slices, setSlices] = useState<Record<Plane, number>>({ axial: 0, coronal: 0, sagittal: 0 });
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [draft, setDraft] = useState<number[][]>([]);
  const volRef = useRef<Volume | null>(null);
  const canvases = { axial: useRef<HTMLCanvasElement>(null), coronal: useRef<HTMLCanvasElement>(null), sagittal: useRef<HTMLCanvasElement>(null) };
  const mipRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    fetch(`${API}/api/workspaces`, { method: "POST" })
      .then((r) => r.json()).then((b) => setWorkspaceId(b.workspace_id)).catch((e) => setError(String(e)));
  }, []);

  const renderPlane = useCallback((plane: Plane) => {
    const vol = volRef.current;
    const cv = canvases[plane].current;
    if (!vol || !cv) return;
    const [w, h] = planeSize(vol.dims, plane);
    cv.width = w; cv.height = h;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(w, h);
    const lo = center - width / 2;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const v = sampleValue(vol, plane, slices[plane], x, y);
        let g = Math.round(((v - lo) / width) * 255);
        g = g < 0 ? 0 : g > 255 ? 255 : g;
        const o = (y * w + x) * 4;
        img.data[o] = img.data[o + 1] = img.data[o + 2] = g; img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    // overlay saved polygons on this plane+slice + the live draft (axial only)
    const drawPoly = (pts: number[][], color: string) => {
      if (pts.length < 2) return;
      ctx.strokeStyle = color; ctx.lineWidth = 0.6; ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      pts.slice(1).forEach((p) => ctx.lineTo(p[0], p[1]));
      ctx.closePath(); ctx.stroke();
    };
    annotations.filter((a) => a.plane === plane && a.slice_index === slices[plane])
      .forEach((a) => drawPoly(a.points, "#39f"));
    if (plane === "axial") drawPoly(draft, "#f80");
  }, [center, width, slices, annotations, draft]);

  useEffect(() => { (["axial", "coronal", "sagittal"] as Plane[]).forEach(renderPlane); }, [renderPlane]);

  const loadVolume = useCallback(async (ctId: string, m: Meta) => {
    const r = await fetch(`${API}/api/ct/${ctId}/volume?max_side=128`);
    const dims = r.headers.get("X-Dims")!.split(",").map(Number) as [number, number, number];
    const buf = await r.arrayBuffer();
    volRef.current = { data: new Int16Array(buf), dims };
    setSlices({ axial: Math.floor(dims[2] / 2), coronal: Math.floor(dims[1] / 2), sagittal: Math.floor(dims[0] / 2) });
    setCenter(m.window_center); setWidth(m.window_width);
    // MIP (basic volume rendering)
    const mr = await fetch(`${API}/api/ct/${ctId}/mip/axial`);
    const shape = mr.headers.get("X-Shape")!.split(",").map(Number);
    const mip = new Float32Array(await mr.arrayBuffer());
    const cv = mipRef.current;
    if (cv) {
      cv.width = shape[0]; cv.height = shape[1];
      const ctx = cv.getContext("2d")!; const img = ctx.createImageData(shape[0], shape[1]);
      let mn = Infinity, mx = -Infinity;
      for (const v of mip) { if (v < mn) mn = v; if (v > mx) mx = v; }
      const rng = mx - mn || 1;
      for (let n = 0; n < mip.length; n++) { const g = Math.round(((mip[n] - mn) / rng) * 255); const o = n * 4; img.data[o] = img.data[o + 1] = img.data[o + 2] = g; img.data[o + 3] = 255; }
      ctx.putImageData(img, 0, 0);
    }
    const anns = await (await fetch(`${API}/api/ct/${ctId}/annotations`)).json();
    setAnnotations(anns);
  }, []);

  const onUpload = useCallback(async (f: File) => {
    if (!workspaceId) return;
    setError(null);
    const fd = new FormData(); fd.append("workspace_id", workspaceId); fd.append("file", f);
    const r = await fetch(`${API}/api/ct/upload`, { method: "POST", body: fd });
    if (!r.ok) { setError(`upload failed: ${(await r.json()).detail ?? r.status}`); return; }
    const m: Meta = await r.json(); setMeta(m); setDraft([]); await loadVolume(m.id, m);
  }, [workspaceId, loadVolume]);

  const onAxialClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cv = canvases.axial.current!; const rect = cv.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * cv.width);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * cv.height);
    setDraft((d) => [...d, [x, y]]);
  };

  const saveAnnotation = useCallback(async () => {
    if (!meta || draft.length < 3) return;
    const r = await fetch(`${API}/api/ct/${meta.id}/annotations`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plane: "axial", slice_index: slices.axial, points: draft, label: "region" }),
    });
    if (r.ok) { setAnnotations((a) => [...a, r.json() as unknown as Annotation]); setDraft([]);
      setAnnotations(await (await fetch(`${API}/api/ct/${meta.id}/annotations`)).json()); }
  }, [meta, draft, slices]);

  const paneStyle = { border: "1px solid #ccc", imageRendering: "pixelated" as const, width: 220, height: 220, background: "#000" };

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>3D CT Viewer (P8)</h2>
      <input type="file" accept=".nii,.nii.gz" onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {meta && (
        <p style={{ fontSize: "0.8rem" }}>
          shape {meta.shape.join("×")} · spacing {meta.spacing.map((s) => s.toFixed(2)).join("/")} · orientation {meta.orientation}
        </p>
      )}
      {meta && (
        <>
          <div style={{ display: "flex", gap: "1rem", margin: "0.5rem 0", fontSize: "0.8rem", flexWrap: "wrap" }}>
            <label>WL {center.toFixed(0)}<input type="range" min={-1000} max={1000} value={center} onChange={(e) => setCenter(+e.target.value)} /></label>
            <label>WW {width.toFixed(0)}<input type="range" min={1} max={2000} value={width} onChange={(e) => setWidth(+e.target.value)} /></label>
          </div>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            {(["axial", "coronal", "sagittal"] as Plane[]).map((p) => (
              <div key={p}>
                <div style={{ fontSize: "0.75rem" }}>{p}{p === "axial" ? " (click to annotate)" : ""}</div>
                <canvas ref={canvases[p]} style={paneStyle} onClick={p === "axial" ? onAxialClick : undefined} />
                <input type="range" min={0} max={(volRef.current?.dims[p === "axial" ? 2 : p === "coronal" ? 1 : 0] ?? 1) - 1}
                  value={slices[p]} onChange={(e) => setSlices((s) => ({ ...s, [p]: +e.target.value }))} style={{ width: 220 }} />
              </div>
            ))}
            <div>
              <div style={{ fontSize: "0.75rem" }}>volume (MIP)</div>
              <canvas ref={mipRef} style={paneStyle} />
            </div>
          </div>
          <div style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
            <button onClick={saveAnnotation} disabled={draft.length < 3}>Save polygon ({draft.length} pts)</button>
            <button onClick={() => setDraft([])} style={{ marginLeft: "0.5rem" }}>Clear</button>
            <span style={{ marginLeft: "1rem" }}>{annotations.length} saved annotation(s)</span>
          </div>
        </>
      )}
      <p style={{ marginTop: "1rem", fontSize: "0.75rem", color: "#666" }}>
        Research and demonstration use only. Not for clinical diagnosis.
      </p>
    </section>
  );
}
