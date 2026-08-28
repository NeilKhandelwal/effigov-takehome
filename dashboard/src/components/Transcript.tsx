"use client";

import { useEffect, useRef } from "react";
import { TranscriptLine } from "@/lib/api";

// Chat-style list: caller on the right, agent on the left. Scrolls to the newest line.
export default function Transcript({ lines, className = "max-h-[60vh]" }: { lines: TranscriptLine[]; className?: string }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div ref={box} className={`${className} overflow-y-auto space-y-3 p-4 rounded-lg bg-slate-50 border border-slate-200`}>
      {lines.length === 0 && <p className="text-slate-500 text-sm">Waiting for the first line…</p>}
      {lines.map((l) => {
        const user = l.role === "user";
        return (
          <div key={l.id} className={`flex ${user ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm shadow-sm ${
                user ? "bg-blue-600 text-white rounded-br-sm" : "bg-white text-slate-900 border border-slate-200 rounded-bl-sm"
              }`}
            >
              <div className={`text-[10px] mb-0.5 ${user ? "text-blue-100" : "text-slate-500"}`}>
                {user ? "Caller" : "Agent"} · {new Date(l.ts).toLocaleTimeString()}
              </div>
              {l.text}
            </div>
          </div>
        );
      })}
    </div>
  );
}
