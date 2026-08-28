import { useEffect, useRef, useState } from "react";

// Hardcoded on purpose: local demo, one backend, no env plumbing yet.
export const API = "http://localhost:8000";

export type Status = "open" | "in_progress" | "resolved";

export type Case = {
  id: string;
  name: string;
  phone: string;
  issue_type: string | null;
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
  status: "active" | "needs_person" | "ended";
  started_at: string;
  ended_at: string | null;
  summary?: string | null; // written by the agent on hang-up (CONTRACT "## Summary")
  room: string | null;
  transfer_reason: string | null; // why the agent handed off (CONTRACT "## Warm transfer")
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

// Staff-side writes on a call: picking up a transfer, ending it, linking a case.
export const patchCall = (id: string, body: Partial<Pick<Call, "status" | "transfer_reason" | "case_id">>) =>
  request<Call>(`/calls/${id}`, json("PATCH", body));

// ---- Browser call (see ../CONTRACT.md "## Browser call") ----

export type Grant = { token: string; url: string; room: string };

export const getToken = (identity: string) =>
  request<Grant>(`/token?identity=${encodeURIComponent(identity)}`);

export const listCallsByRoom = (room: string) =>
  request<Call[]>(`/calls?room=${encodeURIComponent(room)}`);

// ---- Audit log (see ../CONTRACT.md "## Audit") ----

export type CaseEvent = {
  id: number;
  case_id: string;
  field: "created" | "status" | "notes" | "issue_type" | "description" | "call_linked" | "looked_up";
  old_value: string | null;
  new_value: string | null;
  source: "voice" | "staff";
  ts: string;
};

export const getCaseEvents = (id: string) => request<CaseEvent[]>(`/cases/${id}/events`);

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
  return { data, ...since(prev, keys) };
}

// Shared by both trackers: a fresh change wins, otherwise the last set stays alive ~2.5s
// so the flash survives the refetches that land during it.
function since(prev: { changed: Set<string>; at: number }, keys: string[]) {
  if (keys.length) return { changed: new Set(keys), at: Date.now() };
  const fresh = Date.now() - prev.at < 2500;
  return { changed: fresh ? prev.changed : new Set<string>(), at: prev.at };
}

// Same idea one level up: which rows in a list are new or have a newer updated_at.
// changed holds row ids. Nothing flashes on the first load.
export type TrackedList<T> = { data: T[]; changed: Set<string>; at: number };
export const untrackedList = <T,>(): TrackedList<T> => ({ data: [], changed: new Set(), at: 0 });

export function trackList<T extends { id: string; updated_at: string }>(
  prev: TrackedList<T>,
  data: T[],
): TrackedList<T> {
  const before = new Map(prev.data.map((r) => [r.id, r.updated_at]));
  const keys = before.size ? data.filter((r) => before.get(r.id) !== r.updated_at).map((r) => r.id) : [];
  return { data, ...since(prev, keys) };
}

export const flash = (t: Tracked<unknown>, key: string) =>
  `rounded px-1 -mx-1 transition-colors duration-700 ${t.changed.has(key) ? "bg-amber-100 ring-1 ring-amber-300" : ""}`;

// Re-renders the caller once a second so elapsed-time labels (duration()) keep ticking
// between fetches. Returns the tick in case a caller wants the timestamp itself.
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}
