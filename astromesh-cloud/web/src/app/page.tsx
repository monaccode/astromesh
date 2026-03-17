"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    // Will check auth once store is created
    router.replace("/login");
  }, [router]);
  return null;
}
