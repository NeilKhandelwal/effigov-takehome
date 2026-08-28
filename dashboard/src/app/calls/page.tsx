"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Call, ago, duration, listCalls, useLiveRefresh, useNow } from "@/lib/api";

export default function CallsPage() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      listCalls()
        .then((data) => {
          setCalls(data);
          setError(null);
        })
        .catch((e: Error) => setError(e.message)),
    [],
  );

  useEffect(() => {
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [load]);
  useLiveRefresh(load);
  useNow(); // durations tick every second, not only when data arrives

  return (
    <main className="p-6 max-w-6xl mx-auto w-full">
      <h1 className="text-xl font-semibold">Calls</h1>
      <p className="text-sm text-slate-500 mb-4">Every voice session, newest first</p>
      {error && <p className="text-red-700 mb-4 text-sm">{error}</p>}
      <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500 bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="py-2 px-4">Call</th>
              <th className="py-2 px-4">Status</th>
              <th className="py-2 px-4">Started</th>
              <th className="py-2 px-4">Duration</th>
              <th className="py-2 px-4">Case</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="py-2.5 px-4">
                  <Link href={`/calls/${c.id}`} className="font-medium text-blue-700 hover:underline">
                    {c.id}
                  </Link>
                </td>
                <td className="py-2.5 px-4">
                  {c.status === "needs_person" ? (
                    <span
                      title={c.transfer_reason ?? undefined}
                      className="px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-800 ring-1 ring-amber-200"
                    >
                      Needs a person
                    </span>
                  ) : c.status === "active" ? (
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs bg-red-50 text-red-700 ring-1 ring-red-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" /> Live
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600 ring-1 ring-slate-200">Ended</span>
                  )}
                </td>
                <td className="py-2.5 px-4 text-slate-500" title={new Date(c.started_at).toLocaleString()}>
                  {ago(c.started_at)}
                </td>
                <td className="py-2.5 px-4 font-mono text-xs">{duration(c.started_at, c.ended_at)}</td>
                <td className="py-2.5 px-4">
                  {c.case_id ? (
                    <Link href={`/cases/${c.case_id}`} className="text-blue-700 hover:underline">
                      {c.case_id}
                    </Link>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!error && calls.length === 0 && <p className="text-slate-500 text-sm p-4">No calls yet.</p>}
      </div>
    </main>
  );
}
