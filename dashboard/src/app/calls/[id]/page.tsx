"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CallWithTranscript, getCall, useLiveRefresh } from "@/lib/api";
import Transcript from "@/components/Transcript";

export default function CallPage() {
  const { id } = useParams<{ id: string }>();
  const [call, setCall] = useState<CallWithTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      getCall(id)
        .then((data) => {
          setCall(data);
          setError(null);
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

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <Link href="/" className="text-sm text-blue-700 underline">
        &larr; All cases
      </Link>
      <div className="flex items-center gap-3 mt-2 mb-4">
        <h1 className="text-xl font-semibold">Call {id}</h1>
        {call?.status === "active" && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-800 animate-pulse">
            LIVE
          </span>
        )}
        {call?.status === "ended" && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700">ended</span>
        )}
      </div>
      {error && <p className="text-red-700 mb-4">{error}</p>}
      {call && (
        <>
          <p className="text-sm text-gray-500 mb-4">
            Started {new Date(call.started_at).toLocaleString()}
            {call.ended_at && ` · ended ${new Date(call.ended_at).toLocaleTimeString()}`}
            {" · "}
            {call.case_id ? (
              <Link href={`/cases/${call.case_id}`} className="text-blue-700 underline">
                Case {call.case_id}
              </Link>
            ) : (
              "no case linked yet"
            )}
          </p>
          <Transcript lines={call.transcript} />
        </>
      )}
    </main>
  );
}
