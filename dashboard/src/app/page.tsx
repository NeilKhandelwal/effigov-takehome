"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Case,
  CallWithTranscript,
  STATUS_COLOR,
  getCall,
  listCalls,
  listCases,
  useLiveRefresh,
} from "@/lib/api";

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string>("");
  const [live, setLive] = useState<CallWithTranscript[]>([]);

  const load = useCallback(
    () =>
      listCases()
        .then((data) => {
          setCases(data);
          setError(null);
          setRefreshedAt(new Date().toLocaleTimeString());
        })
        .catch((e: Error) => setError(e.message)),
    [],
  );

  // Active calls need their transcript for the "last line" preview; /calls has none.
  const loadLive = useCallback(
    () =>
      listCalls("active")
        .then((calls) => Promise.all(calls.map((c) => getCall(c.id))))
        .then(setLive)
        .catch(() => setLive([])), // backend may predate /calls; not an error worth showing
    [],
  );

  const loadAll = useCallback(() => {
    load();
    loadLive();
  }, [load, loadLive]);

  useEffect(() => {
    loadAll();
    const timer = setInterval(loadAll, 2000); // fallback when the socket is down
    return () => clearInterval(timer);
  }, [loadAll]);
  useLiveRefresh(loadAll);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">Cases</h1>
        <span className="text-xs text-gray-500">
          {refreshedAt ? `last refreshed ${refreshedAt}` : "loading…"}
        </span>
      </div>
      {error && <p className="text-red-700 mb-4">{error}</p>}
      {live.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">
            Live calls
            <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-800">
              {live.length}
            </span>
          </h2>
          <ul className="space-y-1">
            {live.map((c) => {
              const last = c.transcript[c.transcript.length - 1];
              return (
                <li key={c.id} className="flex gap-3 text-sm border rounded px-3 py-2 bg-red-50">
                  <Link href={`/calls/${c.id}`} className="text-blue-700 underline shrink-0">
                    {c.id}
                  </Link>
                  <span className="text-gray-500 shrink-0">
                    {c.case_id ? `case ${c.case_id}` : "no case yet"}
                  </span>
                  <span className="truncate text-gray-800">
                    {last ? `${last.role}: ${last.text}` : "(no transcript yet)"}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      <table className="w-full text-sm">
        <thead className="text-left text-gray-500 border-b">
          <tr>
            <th className="py-2 pr-4">ID</th>
            <th className="py-2 pr-4">Name</th>
            <th className="py-2 pr-4">Issue</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Phone</th>
            <th className="py-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} className="border-b">
              <td className="py-2 pr-4">
                <Link href={`/cases/${c.id}`} className="text-blue-700 underline">
                  {c.id}
                </Link>
              </td>
              <td className="py-2 pr-4">{c.name}</td>
              <td className="py-2 pr-4">{c.issue_type}</td>
              <td className="py-2 pr-4">
                <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_COLOR[c.status]}`}>
                  {c.status}
                </span>
              </td>
              <td className="py-2 pr-4">{c.phone}</td>
              <td className="py-2">{new Date(c.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!error && cases.length === 0 && refreshedAt && (
        <p className="text-gray-500 mt-4">No cases yet.</p>
      )}
    </main>
  );
}
