"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/Shell";
import { useAuth } from "@/lib/auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { ready, token } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  if (!ready) return <p className="p-8 text-[var(--muted)]">Cargando…</p>;
  if (!token) return null;

  return <Shell>{children}</Shell>;
}
