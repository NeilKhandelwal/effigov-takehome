"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Case, STATUSES, STATUS_COLOR, Status, getCase, patchCase } from "@/lib/api";

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setCase] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [dirty, setDirty] = useState(false); // true while the user has unsaved edits

  useEffect(() => {
    const load = () =>
      getCase(id)
        .then((data) => {
          setCase(data);
          setError(null);
          // don't clobber the textarea while the user is editing it
          if (!dirty) setNotes(data.notes);
        })
        .catch((e: Error) => setError(e.message));
    load();
    const timer = setInterval(load, 2000); // poll so voice-driven changes show up
    return () => clearInterval(timer);
  }, [id, dirty]);

  const update = (body: Partial<Case>) =>
    patchCase(id, body)
      .then((data) => {
        setCase(data);
        setError(null);
        return data;
      })
      .catch((e: Error) => setError(e.message));

  const saveNotes = async () => {
    const data = await update({ notes });
    if (data) setDirty(false);
  };

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <Link href="/" className="text-sm text-blue-700 underline">
        &larr; All cases
      </Link>
      <h1 className="text-xl font-semibold mt-2 mb-4">Case {id}</h1>
      {error && <p className="text-red-700 mb-4">{error}</p>}
      {c && (
        <>
          <dl className="grid grid-cols-[10rem_1fr] gap-y-2 text-sm mb-6">
            <dt className="text-gray-500">Name</dt>
            <dd>{c.name}</dd>
            <dt className="text-gray-500">Phone</dt>
            <dd>{c.phone}</dd>
            <dt className="text-gray-500">Issue type</dt>
            <dd>{c.issue_type}</dd>
            <dt className="text-gray-500">Description</dt>
            <dd>{c.description}</dd>
            <dt className="text-gray-500">Status</dt>
            <dd className="flex items-center gap-2">
              <select
                value={c.status}
                onChange={(e) => update({ status: e.target.value as Status })}
                className="border rounded px-2 py-1"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_COLOR[c.status]}`}>
                {c.status}
              </span>
            </dd>
            <dt className="text-gray-500">Created</dt>
            <dd>{new Date(c.created_at).toLocaleString()}</dd>
            <dt className="text-gray-500">Updated</dt>
            <dd>{new Date(c.updated_at).toLocaleString()}</dd>
          </dl>
          <label className="block text-sm text-gray-500 mb-1" htmlFor="notes">
            Notes
          </label>
          <textarea
            id="notes"
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              setDirty(true);
            }}
            rows={6}
            className="w-full border rounded p-2 text-sm"
          />
          <button
            onClick={saveNotes}
            disabled={!dirty}
            className="mt-2 px-3 py-1 rounded bg-blue-700 text-white text-sm disabled:opacity-50"
          >
            Save notes
          </button>
        </>
      )}
    </main>
  );
}
