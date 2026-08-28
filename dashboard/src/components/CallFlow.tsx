import { Fragment } from "react";
import { CallWithTranscript, CaseEvent, duration } from "@/lib/api";

// The journey of one call, left to right: what has happened, what is happening now,
// what is still ahead. Same component on the call page (labelled) and the home
// live cards (compact: dots only, so the card stays the height it was).
type State = "done" | "current" | "pending" | "muted";
type Step = { label: string; caption: string; state: State };

// The agent writes the summary in its shutdown callback, a few seconds after ended_at.
// Until that window passes a missing summary is "still coming", not "never written".
const SUMMARY_GRACE = 15000;

const clock = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const DOT: Record<State, string> = {
  done: "bg-slate-700",
  current: "bg-red-500 animate-pulse",
  pending: "bg-white ring-1 ring-slate-300",
  muted: "bg-slate-200",
};

export default function CallFlow({
  call,
  events,
  now,
  compact,
}: {
  call: CallWithTranscript;
  events?: CaseEvent[]; // events of the linked case; undefined on the home cards
  now: number; // from the caller's useNow(), so the stepper ticks with the rest of the page
  compact?: boolean;
}) {
  const t = now;
  const active = call.status === "active";
  const start = new Date(call.started_at).getTime();
  const end = call.ended_at ? new Date(call.ended_at).getTime() : t;
  const turns = call.transcript.length;

  const linked = events?.find((e) => e.field === "call_linked" && e.new_value === call.id);
  // Fields the agent corrected mid-call, inside this call's window.
  const edits = (events ?? []).filter((e) => {
    const ts = new Date(e.ts).getTime();
    return (
      e.source === "voice" &&
      (e.field === "issue_type" || e.field === "description") &&
      ts >= start &&
      ts <= end
    );
  }).length;

  const steps: Step[] = [
    { label: "Started", caption: clock(call.started_at), state: "done" },
    { label: "Talking", caption: `${turns} turns`, state: turns ? "done" : active ? "current" : "muted" },
    call.case_id
      ? {
          label: "Case linked",
          caption: linked ? `${call.case_id} · +${duration(call.started_at, linked.ts)}` : call.case_id,
          state: "done",
        }
      : { label: active ? "Case linked" : "No case", caption: "", state: active ? "pending" : "muted" },
    {
      label: "Updated",
      caption: edits ? `${edits} voice edit${edits === 1 ? "" : "s"}` : "",
      state: edits ? "done" : "muted",
    },
    { label: "Ended", caption: duration(call.started_at, call.ended_at), state: active ? "current" : "done" },
    call.summary
      ? { label: "Summary", caption: "written", state: "done" }
      : t - end < SUMMARY_GRACE
        ? { label: "Summary", caption: "", state: "pending" }
        : { label: "Summary", caption: "none", state: "muted" },
  ];

  return (
    <div className="flex items-start gap-1.5">
      {steps.map((s, i) => (
        <Fragment key={s.label}>
          {i > 0 && <div className="h-px flex-1 bg-slate-200 mt-1" />}
          <div className="flex flex-col items-center shrink-0 px-0.5">
            <span className={`h-2 w-2 rounded-full ${DOT[s.state]}`} />
            {!compact && (
              <>
                <span className={`mt-1 text-[11px] ${s.state === "muted" ? "text-slate-400" : "text-slate-700"}`}>
                  {s.label}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">{s.caption}</span>
              </>
            )}
          </div>
        </Fragment>
      ))}
    </div>
  );
}
