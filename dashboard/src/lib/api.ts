import { useEffect, useRef, useState } from "react";

// Hardcoded on purpose: local demo, one backend, no env plumbing yet.
export const API = "http://localhost:8000";

export type Status = "open" | "in_progress" | "resolved";

export type Case = {
  id: string;
  name: string;
  phone: string;
  issue_type: string;
  description: string;
  status: Status;
  notes: string;
  created_at: string;
  updated_at: string;
};

export const STATUSES: Status[] = ["open", "in_progress", "resolved"];
export const ISSUE_TYPES = ["missed_pickup", "pothole", "streetlight", "water", "animal", "other"];

export const STATUS_COLOR: Record<Status, string> = {
  open: "bg-blue-50 text-blue-700 ring-blue-200",
  in_progress: "bg-amber-50 text-amber-700 ring-amber-200",
  resolved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

// "missed_pickup" -> "Missed pickup"
export const humanize = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function ago(ts: string) {
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(ts).toLocaleDateString();
}

// "m:ss" between start and end (or now, for a call still in progress)
export function duration(start: string, end: string | null) {
  const s = Math.max(0, ((end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime()) / 1000);
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

export const BACKEND_DOWN = "Backend unreachable at localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API + path, { cache: "no-store", ...init });
  } catch {
    throw new Error(BACKEND_DOWN);
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listCases = () => request<Case[]>("/cases");
export const getCase = (id: string) => request<Case>(`/cases/${id}`);
export const patchCase = (id: string, body: Partial<Case>) =>
  request<Case>(`/cases/${id}`, json("PATCH", body));

// ---- Stretch: calls + transcripts (see ../CONTRACT.md "## Stretch") ----

export type Call = {
  id: string;
  case_id: string | null;
  status: "active" | "ended";
  started_at: string;
  ended_at: string | null;
};

export type TranscriptLine = {
  id: number;
  call_id: string;
  role: "user" | "agent";
  text: string;
  ts: string;
};

export type CallWithTranscript = Call & { transcript: TranscriptLine[] };

export const listCalls = (status?: Call["status"]) =>
  request<Call[]>(status ? `/calls?status=${status}` : "/calls");
export const getCall = (id: string) => request<CallWithTranscript>(`/calls/${id}`);
export const getCaseCalls = (id: string) => request<CallWithTranscript[]>(`/cases/${id}/calls`);

// Subscribes to WS /ws and calls refetch() on every frame (frames carry no payload,
// they just mean "something changed"). Reconnects 2s after close. Callers keep their
// 2s poll as the fallback when the socket is down. Returns whether the socket is up.
export function useLiveRefresh(refetch: () => void) {
  const latest = useRef(refetch);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    latest.current = refetch;
  });
  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let unmounted = false;
    const connect = () => {
      ws = new WebSocket(API.replace(/^http/, "ws") + "/ws");
      ws.onopen = () => setConnected(true);
      ws.onmessage = () => latest.current();
      ws.onclose = () => {
        setConnected(false);
        if (!unmounted) timer = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      unmounted = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);
  return connected;
}

// Change tracking so the UI can flash fields the agent just updated. Pure: use it
// inside a functional setState. Keys stay "changed" for ~2.5s across refetches.
export type Tracked<T> = { data: T | null; changed: Set<string>; at: number };
export const untracked = <T,>(): Tracked<T> => ({ data: null, changed: new Set(), at: 0 });

export function track<T extends object>(prev: Tracked<T>, data: T): Tracked<T> {
  const before = prev.data as Record<string, unknown> | null;
  const keys = before
    ? Object.keys(data).filter((k) => k !== "updated_at" && (data as Record<string, unknown>)[k] !== before[k])
    : [];
  if (keys.length) return { data, changed: new Set(keys), at: Date.now() };
  const fresh = Date.now() - prev.at < 2500;
  return { data, changed: fresh ? prev.changed : new Set(), at: prev.at };
}

export const flash = (t: Tracked<unknown>, key: string) =>
  `rounded px-1 -mx-1 transition-colors duration-700 ${t.changed.has(key) ? "bg-amber-100 ring-1 ring-amber-300" : ""}`;
