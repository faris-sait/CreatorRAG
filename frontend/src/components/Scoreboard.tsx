"use client";

import type { VideoState } from "@/lib/types";

/**
 * Head-to-head engagement-rate comparison — the "pit A against B" payoff.
 * Renders only when both videos are ready and both have an engagement rate.
 * CSS-only bars, no chart dependency.
 */
export default function Scoreboard({
  videoA,
  videoB,
}: {
  videoA: VideoState | null;
  videoB: VideoState | null;
}) {
  const rateA = videoA?.engagement_rate;
  const rateB = videoB?.engagement_rate;
  if (rateA == null || rateB == null) return null;

  const max = Math.max(rateA, rateB, 0.0001);
  const tie = Math.abs(rateA - rateB) < 0.05;
  const winner: "A" | "B" = rateA >= rateB ? "A" : "B";

  const hi = Math.max(rateA, rateB);
  const lo = Math.min(rateA, rateB);
  const diff = hi - lo;
  const ratio = lo > 0 ? hi / lo : null;

  const winnerName =
    (winner === "A" ? videoA?.metadata?.creator : videoB?.metadata?.creator) || `Video ${winner}`;

  const verdict = tie
    ? "Dead heat — engagement rates are level."
    : `Video ${winner} leads by ${diff.toFixed(1)} pts${
        ratio && ratio >= 1.15 ? ` · ${ratio.toFixed(1)}× higher` : ""
      }`;

  return (
    <section
      className="rise rounded-2xl border border-border bg-surface/70 px-4 py-4 backdrop-blur md:px-6 md:py-5"
      style={{ animationDelay: "100ms" }}
      aria-label="Engagement rate comparison"
    >
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-[0.18em] text-text">
          <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
          Engagement scoreboard
        </h2>
        <p className="text-xs text-muted">
          {tie ? (
            <span className="text-faint">{verdict}</span>
          ) : (
            <>
              <span className="text-faint">Winner · </span>
              <span
                className="font-semibold"
                style={{ color: winner === "A" ? "var(--a)" : "var(--b)" }}
              >
                @{winnerName}
              </span>
              <span className="text-faint"> — {diff.toFixed(1)} pts ahead</span>
            </>
          )}
        </p>
      </div>

      <div className="space-y-3">
        <Bar
          slot="A"
          color="var(--a)"
          rate={rateA}
          width={(rateA / max) * 100}
          creator={videoA?.metadata?.creator}
          isWinner={!tie && winner === "A"}
        />
        <Bar
          slot="B"
          color="var(--b)"
          rate={rateB}
          width={(rateB / max) * 100}
          creator={videoB?.metadata?.creator}
          isWinner={!tie && winner === "B"}
        />
      </div>
    </section>
  );
}

function Bar({
  slot,
  color,
  rate,
  width,
  creator,
  isWinner,
}: {
  slot: "A" | "B";
  color: string;
  rate: number;
  width: number;
  creator?: string;
  isWinner: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex w-28 shrink-0 items-center gap-2 sm:w-40">
        <span
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md font-display text-xs font-extrabold"
          style={{ background: `${color}22`, color }}
        >
          {slot}
        </span>
        <span className="truncate text-xs text-muted">@{creator || "unknown"}</span>
      </div>

      <div className="relative h-7 flex-1 overflow-hidden rounded-lg border border-border-soft bg-bg/40">
        <div
          className="h-full rounded-lg transition-[width] duration-700 ease-out"
          style={{
            width: `${Math.max(width, 4)}%`,
            background: `linear-gradient(90deg, ${color}aa, ${color})`,
          }}
        />
        {isWinner && (
          <span
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-bold uppercase tracking-wider"
            style={{ color: "var(--bg)" }}
            aria-hidden
          >
            ★
          </span>
        )}
      </div>

      <div
        className="tabular w-16 shrink-0 text-right text-base font-bold sm:w-20 sm:text-lg"
        style={{ color }}
      >
        {rate}
        <span className="ml-0.5 text-xs text-muted">%</span>
      </div>
    </div>
  );
}
