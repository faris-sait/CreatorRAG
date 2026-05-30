"use client";

import { useState } from "react";
import type { VideoState } from "@/lib/types";
import { compact, duration } from "@/lib/format";
import { videoThumbnail } from "@/lib/api";
import StatusBadge from "./StatusBadge";
import TranscriptModal from "./TranscriptModal";

const PLATFORM_LABEL = { youtube: "YouTube", instagram: "Instagram Reel" };
const WORKING = ["queued", "fetching", "transcribing", "embedding"];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border-soft bg-bg/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className="tabular mt-0.5 text-sm font-semibold text-text">{value}</div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3">
      <div className="skel aspect-video w-full rounded-xl" />
      <div className="skel h-4 w-3/4 rounded" />
      <div className="skel h-3 w-1/2 rounded" />
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skel h-12 rounded-lg" />
        ))}
      </div>
      <div className="skel h-16 rounded-xl" />
    </div>
  );
}

export default function VideoCard({
  slot,
  video,
  onRetry,
}: {
  slot: "A" | "B";
  video: VideoState | null;
  onRetry?: () => void;
}) {
  const [showTranscript, setShowTranscript] = useState(false);
  const accent = slot === "A" ? "var(--a)" : "var(--b)";

  if (!video) {
    return (
      <div
        className="rise flex min-h-[420px] flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-surface/30 p-5 text-center"
        style={{ animationDelay: slot === "A" ? "120ms" : "180ms" }}
      >
        <span
          className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl font-display text-base font-bold"
          style={{ background: `${accent}22`, color: accent }}
        >
          {slot}
        </span>
        <p className="text-sm text-faint">
          Video {slot} appears here once you analyze.
        </p>
      </div>
    );
  }

  const m = video.metadata || {};
  const showSkeleton = WORKING.includes(video.status) && !m.title;

  return (
    <div
      className="rise relative flex-1 overflow-hidden rounded-2xl border border-border bg-surface p-5"
      style={{ animationDelay: slot === "A" ? "120ms" : "180ms" }}
    >
      {/* top accent rule */}
      <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: accent }} />

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-lg font-display text-base font-extrabold"
            style={{ background: `${accent}22`, color: accent }}
          >
            {slot}
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-muted">
            {PLATFORM_LABEL[video.platform]}
          </span>
        </div>
        <StatusBadge status={video.status} />
      </div>

      {video.status === "error" && (
        <div className="mb-4 rounded-xl border border-err/30 bg-err/10 p-3 text-xs text-err">
          <p className="mb-2 break-words">{video.error || "Processing failed"}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="rounded-lg border border-err/40 px-2.5 py-1 font-medium transition hover:bg-err/15"
            >
              ↻ Retry
            </button>
          )}
        </div>
      )}

      {showSkeleton && <Skeleton />}

      {!showSkeleton && (
        <>
          {m.thumbnail && (
            // remote CDN thumbnail — served via backend proxy/persist endpoint
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={videoThumbnail(video.id)}
              alt={m.title || "thumbnail"}
              className="mb-4 aspect-video w-full rounded-xl border border-border-soft object-cover"
            />
          )}

          <h3 className="font-display text-base font-semibold leading-snug text-text line-clamp-2">
            {m.title || "Untitled"}
          </h3>
          <p className="mb-4 mt-1 text-xs text-muted">
            <span style={{ color: accent }}>@{m.creator || "unknown"}</span>
            {" · "}
            <span className="tabular">{compact(m.follower_count)}</span> followers
          </p>

          {/* Engagement scoreboard — the hero metric */}
          <div
            className="mb-4 flex items-end justify-between rounded-xl border px-4 py-3"
            style={{ borderColor: `${accent}55`, background: `${accent}12` }}
          >
            <div className="text-[10px] uppercase leading-tight tracking-[0.18em] text-muted">
              Engagement
              <br />
              rate
            </div>
            <div
              className="tabular text-4xl font-bold leading-none"
              style={{ color: accent }}
            >
              {video.engagement_rate != null ? video.engagement_rate : "—"}
              <span className="ml-0.5 text-lg text-muted">
                {video.engagement_rate != null ? "%" : ""}
              </span>
            </div>
          </div>

          <div className="mb-4 grid grid-cols-3 gap-2">
            <Stat label="Views" value={compact(m.views)} />
            <Stat label="Likes" value={compact(m.likes)} />
            <Stat label="Comments" value={compact(m.comments)} />
            <Stat label="Duration" value={duration(m.duration)} />
            <Stat label="Uploaded" value={m.upload_date || "—"} />
            <Stat label="Chunks" value={String(video.num_chunks ?? "—")} />
          </div>

          {m.hashtags && m.hashtags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {m.hashtags.slice(0, 8).map((h) => (
                <span
                  key={h}
                  className="rounded-md border border-border-soft px-1.5 py-0.5 text-[11px] text-muted"
                >
                  #{h}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {video.status === "ready" && (video.num_chunks ?? 0) > 0 && (
        <button
          onClick={() => setShowTranscript(true)}
          className="mt-4 w-full rounded-xl border border-border py-2 text-xs font-medium text-muted transition hover:border-[color:var(--accent)] hover:text-text"
        >
          ↳ View transcript
        </button>
      )}

      {m.source && (
        <p className="mt-3 font-mono text-[10px] text-faint">{m.source}</p>
      )}

      {showTranscript && (
        <TranscriptModal
          slot={slot}
          videoId={video.id}
          onClose={() => setShowTranscript(false)}
        />
      )}
    </div>
  );
}
