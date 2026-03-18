"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchSettings } from "@/lib/api";

/**
 * Checks whether the basic setup wizard has been completed.
 * If not, redirects to /setup (unless already on the setup page).
 */
export function SetupGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    // Don't check if already on the setup page
    if (pathname === "/setup") {
      setChecked(true);
      return;
    }

    fetchSettings()
      .then((settings) => {
        if (!settings.basic_wizard_completed) {
          setShowBanner(true);
          router.push("/setup");
        }
      })
      .catch(() => {
        // If settings fetch fails (e.g. server not running), let the app load normally
      })
      .finally(() => setChecked(true));
  }, [pathname, router]);

  if (!checked) {
    return null;
  }

  return (
    <>
      {showBanner && pathname !== "/setup" && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
          Setup not complete.{" "}
          <a href="/setup" className="font-medium underline underline-offset-2">
            Run the setup wizard
          </a>{" "}
          to get started.
        </div>
      )}
      {children}
    </>
  );
}
