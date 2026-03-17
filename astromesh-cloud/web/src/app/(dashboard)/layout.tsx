"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { Sidebar } from "@/components/ui/Sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const orgSlug = useAuthStore((s) => s.orgSlug);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
    }
  }, [token, router]);

  // Render nothing while redirecting
  if (!token || !orgSlug) return null;

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "??";

  return (
    <div className="min-h-screen bg-am-bg text-am-text">
      <Sidebar orgSlug={orgSlug} orgName={orgSlug} />

      {/* Offset main content by sidebar width */}
      <div className="ml-56 flex flex-col min-h-screen">
        {/* Header */}
        <header className="sticky top-0 z-20 flex items-center justify-end gap-3 border-b border-am-border bg-am-bg/80 backdrop-blur px-6 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-am-cyan-dim border border-am-cyan/30 text-xs font-semibold text-am-cyan">
              {initials}
            </div>
            <span className="text-sm text-am-text-dim">{user?.name ?? user?.email ?? "Unknown"}</span>
          </div>

          <button
            onClick={handleLogout}
            className="rounded-md border border-am-border px-3 py-1.5 text-xs text-am-text-dim hover:border-am-border-hover hover:text-am-text transition-all"
          >
            Logout
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 px-6 py-8 max-w-6xl mx-auto w-full">{children}</main>
      </div>
    </div>
  );
}
