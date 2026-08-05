"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  CheckCircle,
  FileText,
  Rocket,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/jobs", label: "All Jobs", icon: Briefcase },
  { href: "/applied", label: "Applied", icon: CheckCircle },
  { href: "/generate", label: "Generate Resume", icon: FileText },
  { href: "/auto-apply", label: "Auto Apply", icon: Rocket },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-white border-r border-slate-200">
      {/* Header */}
      <div className="flex flex-col gap-1 px-6 pt-8 pb-6">
        <h1 className="text-xl font-bold gradient-text">Job Hunter</h1>
        <p className="text-xs text-text-muted">AI-powered job pipeline</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-indigo-50 text-primary-light border-l-2 border-primary"
                  : "text-text-secondary hover:text-text-primary hover:bg-slate-50 border-l-2 border-transparent"
              )}
            >
              <item.icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-slate-200">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <span className="status-dot" />
          <span>System online</span>
        </div>
        <p className="mt-1 text-[10px] text-text-muted/60">v1.0.0</p>
      </div>
    </aside>
  );
}
