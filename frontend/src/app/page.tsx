"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import VideoCard from "@/components/VideoCard";
import ChatPanel from "@/components/ChatPanel";
import Scoreboard from "@/components/Scoreboard";
import { getPairStatus, submitVideos } from "@/lib/api";
import type { PairStatus } from "@/lib/types";

const GITHUB_URL = "https://github.com/faris-sait/CreatorRAG";
const ARCHITECTURE_URL = "/architecture.html";

// Placeholders only — inputs start empty so pasted URLs can't get glued onto a
// pre-filled value. Everything downstream is computed dynamically.
const PLACEHOLDER_YT = "https://www.youtube.com/watch?v=…";
const PLACEHOLDER_IG = "https://www.instagram.com/reel/…";

const TERMINAL = new Set(["ready", "error"]);

export default function Home() {
  const [yt, setYt] = useState("");
  const [ig, setIg] = useState("");
  const [exactYt, setExactYt] = useState(false);
  const [pairId, setPairId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [status, setStatus] = useState<PairStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async (id: string) => {
    try {
      const s = await getPairStatus(id);
      setStatus(s);
      const a = s.video_a?.status;
      const b = s.video_b?.status;
      if (a && b && TERMINAL.has(a) && TERMINAL.has(b) && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      /* transient — keep polling */
    }
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    await analyze();
  }

  async function analyze() {
    if (!yt.trim() || !ig.trim()) {
      setError("Please paste both a YouTube and an Instagram URL.");
      return;
    }
    setError(null);
    setSubmitting(true);
    setStatus(null);
    if (pollRef.current) clearInterval(pollRef.current);
    try {
      const { pair_id } = await submitVideos(yt, ig, exactYt);
      setPairId(pair_id);
      setSessionId(crypto.randomUUID());
      await poll(pair_id);
      pollRef.current = setInterval(() => poll(pair_id), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  const ready = !!status?.ready;

  return (
    <main className="mx-auto flex min-h-screen max-w-[1400px] flex-col gap-6 px-5 py-7 md:px-8">
      {/* Masthead */}
      <header className="rise flex flex-wrap items-end justify-between gap-4 border-b border-border-soft pb-5">
        <div>
          <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.25em] text-faint">
            <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
            creator analytics
          </div>
          <h1 className="font-display text-4xl font-extrabold leading-none tracking-tight text-text md:text-5xl">
            Creato<span className="text-accent">Flow</span>
          </h1>
        </div>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:max-w-sm sm:items-end">
          <nav className="flex flex-wrap items-center gap-2">
            <NavLink href={ARCHITECTURE_URL}>Architecture</NavLink>
            <NavLink href={GITHUB_URL}>GitHub ↗</NavLink>
          </nav>
          <p className="text-sm leading-relaxed text-muted sm:text-right">
            Pit a <span className="text-a">YouTube</span> video against an{" "}
            <span className="text-b">Instagram Reel</span> — real metrics, transcripts,
            and a chat that cites its sources.
          </p>
        </div>
      </header>

      {/* Submit console */}
      <form
        onSubmit={onSubmit}
        className="rise rounded-2xl border border-border bg-surface/70 p-4 backdrop-blur md:p-5"
        style={{ animationDelay: "60ms" }}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1fr_auto]">
          <Field
            label="Video A · YouTube"
            color="var(--a)"
            value={yt}
            onChange={setYt}
            placeholder={PLACEHOLDER_YT}
          />
          <Field
            label="Video B · Instagram"
            color="var(--b)"
            value={ig}
            onChange={setIg}
            placeholder={PLACEHOLDER_IG}
          />
          <div className="flex items-end">
            <button
              type="submit"
              disabled={submitting}
              className="h-[42px] w-full rounded-xl bg-accent px-6 font-display text-sm font-bold tracking-wide text-black transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50 md:w-auto"
            >
              {submitting ? "Analyzing…" : "Analyze →"}
            </button>
          </div>
        </div>
        <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={exactYt}
            onChange={(e) => setExactYt(e.target.checked)}
            className="accent-accent"
          />
          Exact YouTube timestamps{" "}
          <span className="text-faint">(slower — uses subtitles, not the fast transcript)</span>
        </label>
      </form>

      {error && (
        <p className="rise rounded-xl border border-err/30 bg-err/10 px-4 py-3 text-sm text-err">
          {error}
        </p>
      )}

      {/* Head-to-head engagement comparison (self-hides until both ready) */}
      <Scoreboard videoA={status?.video_a ?? null} videoB={status?.video_b ?? null} />

      {/* Arena */}
      <div className="grid flex-1 grid-cols-1 gap-5 lg:grid-cols-[1fr_1fr_minmax(380px,440px)]">
        <VideoCard slot="A" video={status?.video_a ?? null} onRetry={analyze} />
        <VideoCard slot="B" video={status?.video_b ?? null} onRetry={analyze} />
        <div className="min-h-[480px] lg:h-auto">
          <ChatPanel
            pairId={pairId}
            sessionId={sessionId}
            ready={ready}
            videoA={status?.video_a ?? null}
            videoB={status?.video_b ?? null}
            onNewChat={() => setSessionId(crypto.randomUUID())}
          />
        </div>
      </div>

      {/* Footer */}
      <footer className="rise mt-1 flex flex-wrap items-center justify-between gap-3 border-t border-border-soft pt-5 text-xs text-faint">
        <span>
          Built for <span className="text-muted">CreatorJoy</span> · YouTube vs Instagram Reel
        </span>
        <div className="flex gap-4">
          <a href={ARCHITECTURE_URL} target="_blank" rel="noopener noreferrer" className="transition hover:text-text">
            Architecture
          </a>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="transition hover:text-text">
            GitHub
          </a>
        </div>
      </footer>
    </main>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-muted transition hover:border-[color:var(--accent)] hover:text-text"
    >
      {children}
    </a>
  );
}

function Field({
  label,
  color,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  color: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div>
      <label className="mb-1.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted">
        <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: color }} />
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="w-full rounded-xl border border-border bg-bg/60 px-3.5 py-2.5 font-mono text-sm text-text outline-none transition placeholder:text-faint focus:border-accent/60 focus:ring-2 focus:ring-accent/15"
      />
    </div>
  );
}
