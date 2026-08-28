"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Case, STATUS_COLOR, listCases } from "@/lib/api";

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string>("");

  useEffect(() => {
    const load = () =>
      listCases()
        .then((data) => {
          setCases(data);
          setError(null);
          setRefreshedAt(new Date().toLocaleTimeString());
        })
        .catch((e: Error) => setError(e.message));
    load();
    const timer = setInterval(load, 2000); // poll so agent-created cases show up
    return () => clearInterval(timer);
  }, []);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">Cases</h1>
        <span className="text-xs text-gray-500">
          {refreshedAt ? `last refreshed ${refreshedAt}` : "loading…"}
        </span>
      </div>
      {error && <p className="text-red-700 mb-4">{error}</p>}
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
