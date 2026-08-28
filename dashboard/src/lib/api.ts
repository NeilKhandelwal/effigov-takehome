import { useEffect, useRef } from "react";

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

export const STATUS_COLOR: Record<Status, string> = {
  open: "bg-blue-100 text-blue-800",
  in_progress: "bg-amber-100 text-amber-800",
  resolved: "bg-green-100 text-green-800",
};

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

export const listCases = () => request<Case[]>("/cases");

export const getCase = (id: string) => request<Case>(`/cases/${id}`);

export const patchCase = (id: string, body: Partial<Case>) =>
  request<Case>(`/cases/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

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
// 2s poll as the fallback when the socket is down.
export function useLiveRefresh(refetch: () => void) {
  const latest = useRef(refetch);
  useEffect(() => {
    latest.current = refetch;
  });
  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let unmounted = false;
    const connect = () => {
      ws = new WebSocket(API.replace(/^http/, "ws") + "/ws");
      ws.onmessage = () => latest.current();
      ws.onclose = () => {
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
}
