import type { VideoStatus } from "@/lib/types";

const LABELS: Record<VideoStatus, string> = {
  queued: "Queued",
  fetching: "Fetching",
  transcribing: "Transcribing",
  embedding: "Embedding",
  ready: "Ready",
  error: "Error",
};

// [text, dot] colors per status (CSS vars / rgba on the dark surface).
const STYLES: Record<VideoStatus, { fg: string; bg: string }> = {
  queued: { fg: "#a8a8b3", bg: "rgba(168,168,179,0.12)" },
  fetching: { fg: "#7dd3fc", bg: "rgba(125,211,252,0.12)" },
  transcribing: { fg: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  embedding: { fg: "#c4b5fd", bg: "rgba(196,181,253,0.12)" },
  ready: { fg: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  error: { fg: "#f87171", bg: "rgba(248,113,113,0.12)" },
};

const isWorking = (s: VideoStatus) =>
  s === "queued" || s === "fetching" || s === "transcribing" || s === "embedding";

export default function StatusBadge({ status }: { status: VideoStatus }) {
  const c = STYLES[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
      style={{ color: c.fg, background: c.bg }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${isWorking(status) ? "live-dot" : ""}`}
        style={{ background: c.fg }}
      />
      {LABELS[status]}
    </span>
  );
}
