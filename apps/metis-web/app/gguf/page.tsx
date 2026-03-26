"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GgufPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/settings?tab=models");
  }, [router]);
  return null;
}
