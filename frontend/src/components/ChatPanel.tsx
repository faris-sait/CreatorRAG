"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { streamChat } from "@/lib/api";
import type { ChatMessage, Citation, VideoState } from "@/lib/types";

const QUICK_PROMPTS = [
  "Why did Video A get more engagement than Video B?",
  "What's the engagement rate of each?",
  "Compare the hooks in the first 5 seconds.",
  "Who's the creator of Video B and what's their follower count?",
  "Suggest improvements for B based on what worked in A.",
];

/** Deep-link a citation to the source video (YouTube jumps to the timestamp). */
function citationHref(
  c: Citation,
  videoA: VideoState | null,
  videoB: VideoState | null,
): string | undefined {
  const v = c.video === "A" ? videoA : videoB;
  if (!v?.url) return undefined;
  if (v.platform === "youtube" && c.start != null) {
    return `${v.url}&t=${Math.floor(c.start)}s`;
  }
  return v.url;
}

function CitationChips({
  sources,
  videoA,
  videoB,
}: {
  sources: Citation[];
  videoA: VideoState | null;
  videoB: VideoState | null;
}) {
  if (!sources?.length) return null;
  return (
    <div className="mt-3 border-t border-border-soft pt-2.5">
      <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-faint">
        Sources
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((s, i) => {
          const href = citationHref(s, videoA, videoB);
          const color = s.video === "A" ? "var(--a)" : "var(--b)";
          return (
            <a
              key={i}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              title={s.text}
              className="group inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition hover:brightness-110"
              style={{ borderColor: `${color}40`, background: `${color}12`, color }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
              Video {s.video}
              <span className="tabular opacity-70">{s.timestamp}</span>
              <span className="opacity-50 transition group-hover:opacity-100">↗</span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

// Tailwind-styled markdown elements (no typography plugin needed).
const MD = {
  p: (p: React.HTMLAttributes<HTMLParagraphElement>) => <p className="mb-2 last:mb-0" {...p} />,
  ul: (p: React.HTMLAttributes<HTMLUListElement>) => <ul className="mb-2 list-disc pl-4" {...p} />,
  ol: (p: React.HTMLAttributes<HTMLOListElement>) => <ol className="mb-2 list-decimal pl-4" {...p} />,
  li: (p: React.HTMLAttributes<HTMLLIElement>) => <li className="mb-1" {...p} />,
  strong: (p: React.HTMLAttributes<HTMLElement>) => (
    <strong className="font-semibold text-text" {...p} />
  ),
  code: (p: React.HTMLAttributes<HTMLElement>) => (
    <code className="rounded bg-bg/70 px-1 py-0.5 font-mono text-[12px] text-accent" {...p} />
  ),
};

export default function ChatPanel({
  pairId,
  sessionId,
  ready,
  videoA,
  videoB,
  onNewChat,
}: {
  pairId: string | null;
  sessionId: string;
  ready: boolean;
  videoA: VideoState | null;
  videoB: VideoState | null;
  onNewChat?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  // New session (or new analysis) → clear the transcript of this chat.
  useEffect(() => {
    setMessages([]);
  }, [sessionId]);

  async function send(text: string) {
    if (!text.trim() || !pairId || busy) return;
    setBusy(true);
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { role: "assistant", content: "", streaming: true },
    ]);

    const update = (fn: (msg: ChatMessage) => ChatMessage) =>
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });

    await streamChat(pairId, sessionId, text, {
      onToken: (t) => update((msg) => ({ ...msg, content: msg.content + t })),
      onSources: (s) => update((msg) => ({ ...msg, sources: s })),
      onDone: () => update((msg) => ({ ...msg, streaming: false })),
      onError: (e) =>
        update((msg) => ({
          ...msg,
          content: msg.content || `⚠️ ${e}`,
          streaming: false,
        })),
    });
    setBusy(false);
  }

  return (
    <div
      className="rise flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface"
      style={{ animationDelay: "240ms" }}
    >
      <div className="flex items-start justify-between border-b border-border-soft px-4 py-3.5">
        <div>
          <h2 className="flex items-center gap-2 font-display text-sm font-bold tracking-wide text-text">
            <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
            RAG CHAT
          </h2>
          <p className="mt-0.5 text-[11px] leading-snug text-faint">
            {ready
              ? "Streamed, cited, and remembers the conversation."
              : "Waiting for both videos to finish processing…"}
          </p>
        </div>
        {messages.length > 0 && onNewChat && (
          <button
            onClick={onNewChat}
            disabled={busy}
            className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-[11px] text-muted transition hover:border-[color:var(--accent)] hover:text-text disabled:opacity-40"
          >
            + New chat
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="mb-2 text-[11px] uppercase tracking-wider text-faint">
              Try asking
            </p>
            {QUICK_PROMPTS.map((p) => (
              <button
                key={p}
                disabled={!ready}
                onClick={() => send(p)}
                className="block w-full rounded-xl border border-border-soft bg-bg/40 px-3 py-2.5 text-left text-[13px] text-muted transition hover:border-[color:var(--accent)]/60 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                m.role === "user"
                  ? "bg-accent font-medium text-black"
                  : "border border-border-soft bg-bg/50 text-text"
              }`}
            >
              {m.role === "assistant" ? (
                <div className="md">
                  <ReactMarkdown components={MD}>{m.content}</ReactMarkdown>
                  {m.streaming && <span className="caret" />}
                </div>
              ) : (
                <div className="whitespace-pre-wrap">{m.content}</div>
              )}
              {m.role === "assistant" && m.sources && (
                <CitationChips sources={m.sources} videoA={videoA} videoB={videoB} />
              )}
            </div>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 border-t border-border-soft p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={!ready || busy}
          placeholder={ready ? "Ask about A or B…" : "Processing videos…"}
          className="flex-1 rounded-xl border border-border bg-bg/60 px-3.5 py-2.5 text-[13px] text-text outline-none transition placeholder:text-faint focus:border-accent/60 focus:ring-2 focus:ring-accent/15 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!ready || busy || !input.trim()}
          className="rounded-xl bg-accent px-4 font-display text-sm font-bold text-black transition hover:brightness-110 active:scale-95 disabled:opacity-40"
        >
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
