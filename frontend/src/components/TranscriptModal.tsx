"use client";

import { useEffect, useState } from "react";
import { getTranscript } from "@/lib/api";
import { duration } from "@/lib/format";
import type { Transcript } from "@/lib/types";

export default function TranscriptModal({
  slot,
  videoId,
  onClose,
}: {
  slot: "A" | "B";
  videoId: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTranscript(videoId).then(setData).catch((e) => setError(String(e)));
  }, [videoId]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const accent = slot === "A" ? "var(--a)" : "var(--b)";
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-soft px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <span
              className="flex h-7 w-7 items-center justify-center rounded-lg font-display text-sm font-bold"
              style={{ background: `${accent}22`, color: accent }}
            >
              {slot}
            </span>
            <div>
              <h3 className="font-display text-sm font-bold text-text">Transcript</h3>
              <p className="line-clamp-1 text-xs text-faint">{data?.title || ""}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-muted transition hover:bg-bg hover:text-text"
          >
            ✕
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          {error && <p className="text-sm text-err">{error}</p>}
          {!data && !error && (
            <p className="text-sm text-faint">Loading transcript…</p>
          )}
          {data && data.chunks.length > 0 ? (
            <div className="space-y-3">
              {data.chunks.map((c) => (
                <div key={c.chunk_index} className="flex gap-3">
                  <span
                    className="tabular h-fit shrink-0 rounded-md border px-1.5 py-0.5 text-[11px]"
                    style={{ borderColor: `${accent}44`, color: accent }}
                  >
                    {c.start !== null ? duration(c.start) : "—"}
                  </span>
                  <p className="text-[13px] leading-relaxed text-muted">{c.text}</p>
                </div>
              ))}
            </div>
          ) : (
            data && (
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-muted">
                {data.transcript || "No transcript available."}
              </p>
            )
          )}
        </div>

        <div className="border-t border-border-soft px-5 py-2.5 text-right text-[11px] text-faint">
          {data
            ? `${data.chunks.length} chunk(s) · exactly what the chat retrieves & cites`
            : ""}
        </div>
      </div>
    </div>
  );
}
