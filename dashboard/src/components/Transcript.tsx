"use client";

import { useEffect, useRef } from "react";
import { TranscriptLine } from "@/lib/api";

// Chat-style list: user on the right, agent on the left. Scrolls to the newest line.
export default function Transcript({ lines }: { lines: TranscriptLine[] }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div ref={box} className="max-h-[70vh] overflow-y-auto space-y-2 p-2 border rounded bg-white">
      {lines.length === 0 && <p className="text-gray-500 text-sm">No transcript yet.</p>}
      {lines.map((l) => (
        <div key={l.id} className={`flex ${l.role === "user" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
              l.role === "user" ? "bg-blue-100 text-blue-900" : "bg-gray-100 text-gray-900"
            }`}
          >
            <div className="text-[10px] text-gray-500 mb-0.5">
              {l.role} · {new Date(l.ts).toLocaleTimeString()}
            </div>
            {l.text}
          </div>
        </div>
      ))}
    </div>
  );
}
