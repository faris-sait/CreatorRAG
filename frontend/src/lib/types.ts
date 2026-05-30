export type VideoStatus =
  | "queued"
  | "fetching"
  | "transcribing"
  | "embedding"
  | "ready"
  | "error";

export interface VideoMeta {
  title?: string;
  creator?: string;
  follower_count?: number | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  hashtags?: string[];
  upload_date?: string | null;
  duration?: number | null;
  thumbnail?: string | null;
  source?: string;
}

export interface VideoState {
  id: string;
  url: string;
  platform: "youtube" | "instagram";
  status: VideoStatus;
  error?: string | null;
  engagement_rate?: number | null;
  num_chunks?: number | null;
  metadata: VideoMeta;
}

export interface PairStatus {
  pair_id: string;
  ready: boolean;
  video_a: VideoState | null;
  video_b: VideoState | null;
}

export interface TranscriptChunk {
  chunk_index: number;
  start: number | null;
  end: number | null;
  text: string;
}

export interface Transcript {
  id: string;
  platform: "youtube" | "instagram";
  title?: string | null;
  transcript: string;
  chunks: TranscriptChunk[];
}

export interface Citation {
  video: "A" | "B";
  chunk_index: number;
  start: number | null;
  end: number | null;
  timestamp: string;
  text: string;
  score: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Citation[];
  streaming?: boolean;
}
