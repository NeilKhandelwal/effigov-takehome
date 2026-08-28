"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLiveRefresh } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Cases" },
  { href: "/calls", label: "Calls" },
];

export default function Nav() {
  const path = usePathname();
  const live = useLiveRefresh(() => {}); // only here to show connection state

  return (
    <header className="bg-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-8">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="font-semibold tracking-tight text-lg">EffiGov</span>
          <span className="text-slate-400 text-sm">Case Desk</span>
        </Link>
        <nav className="flex gap-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`px-3 py-1.5 rounded-md ${active ? "bg-slate-700 text-white" : "text-slate-300 hover:text-white hover:bg-slate-800"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <span className="ml-auto flex items-center gap-2 text-xs text-slate-300">
          <span className={`h-2 w-2 rounded-full ${live ? "bg-emerald-400" : "bg-amber-400"}`} />
          {live ? "Live" : "Polling"}
        </span>
      </div>
    </header>
  );
}
