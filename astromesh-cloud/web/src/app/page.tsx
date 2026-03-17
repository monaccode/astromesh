"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";

export default function Home() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  useEffect(() => {
    router.replace(token ? "/agents" : "/login");
  }, [token, router]);
  return null;
}
