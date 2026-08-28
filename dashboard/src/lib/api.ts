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
