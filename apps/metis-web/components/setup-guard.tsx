"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchSettings } from "@/lib/api";

/**
 * Checks whether the basic setup wizard has been completed.
 * The welcome hub, diagnostics, and setup flow remain accessible before setup.
 */
export function SetupGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checkedPath, setCheckedPath] = useState<string | null>(null);
  const allowedBeforeSetup = useMemo(
    () => new Set(["/", "/setup", "/diagnostics", "/design"]),
    [],
  );
  const checked = allowedBeforeSetup.has(pathname) || checkedPath === pathname;

  useEffect(() => {
    if (allowedBeforeSetup.has(pathname)) {
      return;
    }

    fetchSettings()
      .then((settings) => {
        if (!settings.basic_wizard_completed) {
          router.replace("/setup");
        }
      })
      .catch(() => {
        // If settings fetch fails (e.g. server not running), let the app load normally.
      })
      .finally(() => setCheckedPath(pathname));
  }, [allowedBeforeSetup, pathname, router]);

  if (!checked) {
    return null;
  }

  return <>{children}</>;
}
