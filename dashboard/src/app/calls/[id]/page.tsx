"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Case,
  CallWithTranscript,
  STATUS_COLOR,
  Tracked,
  duration,
  flash,
  getCall,
  getCase,
  humanize,
  patchCall,
  track,
  untracked,
  useLiveRefresh,
  useNow,
} from "@/lib/api";
import Transcript from "@/components/Transcript";

export default function CallPage() {
  const { id } = useParams<{ id: string }>();
  const [call, setCall] = useState<CallWithTranscript | null>(null);
  const [c, setCase] = useState<Tracked<Case>>(untracked);
  const [error, setError] = useState<string | null>(null);
  const [pickingUp, setPickingUp] = useState(false);

  const load = useCallback(
    () =>
      getCall(id)
        .then((data) => {
          setCall(data);
          setError(null);
          // The linked case sits beside the transcript so staff see fields fill in as the agent learns them.
          return data.case_id ? getCase(data.case_id).then((cs) => setCase((prev) => track(prev, cs))) : setCase(untracked());
        })
        .catch((e: Error) => setError(e.message)),
    [id],
  );

  useEffect(() => {
    load();
    const timer = setInterval(load, 2000); // fallback when the socket is down
    return () => clearInterval(timer);
  }, [load]);
  useLiveRefresh(load);
  useNow(); // durations tick every second, not only when data arrives

  // needs_person is still a call in progress: the line is open, staff just haven't taken it yet
  const live = !!call && call.status !== "ended";
  const needsPerson = call?.status === "needs_person";
  const cs = c.data;

  const pickUp = async () => {
    setPickingUp(true);
    try {
      await patchCall(id, { status: "active" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPickingUp(false);
    }
  };

  return (
    <main className="p-6 max-w-6xl mx-auto w-full">
      <Link href="/calls" className="text-sm text-blue-700 hover:underline">
        &larr; All calls
      </Link>
      <div className="flex items-center gap-3 mt-2 mb-4">
        <h1 className="text-xl font-semibold">Call {id}</h1>
        {call && (
          needsPerson ? (
            <span className="px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-800 ring-1 ring-amber-200">
              Needs a person
            </span>
          ) : live ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs bg-red-50 text-red-700 ring-1 ring-red-200">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" /> LIVE
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600 ring-1 ring-slate-200">Ended</span>
          )
        )}
        {needsPerson && (
          <>
            {call?.transfer_reason && <span className="text-sm text-amber-800">{call.transfer_reason}</span>}
            <button
              onClick={pickUp}
              disabled={pickingUp}
              className="px-2.5 py-1 rounded-md bg-slate-900 text-white text-xs disabled:opacity-40"
            >
              Picked up
            </button>
          </>
        )}
        {call && (
          <span className="text-sm text-slate-500">
            {new Date(call.started_at).toLocaleTimeString()} · <span className="font-mono">{duration(call.started_at, call.ended_at)}</span>
            {" · "}{call.transcript.length} lines
          </span>
        )}
      </div>
      {error && <p className="text-red-700 mb-4 text-sm">{error}</p>}

      {call && (
        <div className="grid md:grid-cols-3 gap-4">
          <section className="md:col-span-2">
            {call.summary && (
              <p className="mb-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm italic text-slate-600">
                {call.summary}
              </p>
            )}
            <Transcript lines={call.transcript} className="max-h-[70vh] min-h-64" active={live} />
          </section>

          <aside className="rounded-lg border border-slate-200 bg-white shadow-sm p-4 text-sm h-fit">
            <h2 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Case</h2>
            {!cs ? (
              <p className="text-slate-500">
                No case linked yet. The agent links one once it creates or looks up a case.
              </p>
            ) : (
              <dl className="space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-500">ID</dt>
                  <dd>
                    <Link href={`/cases/${cs.id}`} className="font-medium text-blue-700 hover:underline">
                      {cs.id}
                    </Link>
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Status</dt>
                  <dd className={flash(c, "status")}>
                    <span className={`px-2 py-0.5 rounded-full text-xs ring-1 ${STATUS_COLOR[cs.status]}`}>{humanize(cs.status)}</span>
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Resident</dt>
                  <dd className={flash(c, "name")}>{cs.name}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Phone</dt>
                  <dd className={`font-mono text-xs ${flash(c, "phone")}`}>{cs.phone}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Issue</dt>
                  <dd className={flash(c, "issue_type")}>{humanize(cs.issue_type)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 mb-0.5">Description</dt>
                  <dd className={flash(c, "description")}>{cs.description}</dd>
                </div>
                {cs.notes && (
                  <div>
                    <dt className="text-slate-500 mb-0.5">Notes</dt>
                    <dd className={`whitespace-pre-wrap ${flash(c, "notes")}`}>{cs.notes}</dd>
                  </div>
                )}
              </dl>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}
