"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSettings, updateSettings } from "@/lib/api";
import {
  capUserStars,
  CONSTELLATION_USER_STAR_LIMIT,
  getRemainingUserStarSlots,
  type UserStar,
  normalizeUserStar,
  parseUserStars,
} from "@/lib/constellation-types";

const STORAGE_KEY = "metis_constellation_user_stars";
const SETTINGS_KEY = "landing_constellation_user_stars";

function persistLocal(stars: UserStar[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stars));
  } catch {
    // Ignore local storage write errors and keep runtime state.
  }
}

function readLocal(): UserStar[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    return parseUserStars(JSON.parse(raw));
  } catch {
    return [];
  }
}

export function useConstellationStars() {
  const [userStars, setUserStars] = useState<UserStar[]>([]);
  const [syncError, setSyncError] = useState<string | null>(null);
  const initializedRef = useRef(false);
  const userStarsRef = useRef<UserStar[]>([]);

  useEffect(() => {
    userStarsRef.current = userStars;
  }, [userStars]);

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;

    const local = readLocal();
    if (local.length > 0) {
      setUserStars(capUserStars(local));
      return;
    }

    fetchSettings()
      .then((settings) => {
        const fromApi = parseUserStars(settings[SETTINGS_KEY]);
        const capped = capUserStars(fromApi);
        setUserStars(capped);
        persistLocal(capped);
      })
      .catch((error) => {
        console.error("Failed to load constellation stars from settings", error);
        // Keep empty fallback when API is unavailable.
      });
  }, []);

  const saveBoth = useCallback(async (nextStars: UserStar[]) => {
    const capped = capUserStars(nextStars);
    setUserStars(capped);
    userStarsRef.current = capped;
    persistLocal(capped);
    setSyncError(null);
    try {
      await updateSettings({ [SETTINGS_KEY]: capped });
    } catch (error) {
      console.error("Failed to sync constellation stars to settings", error);
      setSyncError("Unable to sync stars to settings. Using local cache only.");
    }
  }, []);

  const addUserStar = useCallback(
    async (star: Omit<UserStar, "id" | "createdAt">) => {
      const current = userStarsRef.current;
      const remainingSlots = getRemainingUserStarSlots(current.length);
      if (remainingSlots === 0) {
        return false;
      }
      const now = Date.now();
      const next = [
        ...current,
        normalizeUserStar({
          ...star,
          id: `star-${now}-${Math.round(Math.random() * 100000)}`,
          createdAt: now,
        }),
      ];
      await saveBoth(next);
      return true;
    },
    [saveBoth],
  );

  const addUserStars = useCallback(
    async (stars: Array<Omit<UserStar, "id" | "createdAt">>) => {
      const current = userStarsRef.current;
      const remainingSlots = getRemainingUserStarSlots(current.length);
      if (remainingSlots === 0) {
        return 0;
      }

      const now = Date.now();
      const starsToAdd = remainingSlots === null ? stars : stars.slice(0, remainingSlots);
      const nextStars = starsToAdd.map((star, index) =>
        normalizeUserStar({
          ...star,
          id: `star-${now}-${index}-${Math.round(Math.random() * 100000)}`,
          createdAt: now + index,
        }),
      );
      if (nextStars.length === 0) {
        return 0;
      }

      await saveBoth([...current, ...nextStars]);
      return nextStars.length;
    },
    [saveBoth],
  );

  const removeLastUserStar = useCallback(async () => {
    if (userStars.length === 0) {
      return;
    }
    await saveBoth(userStars.slice(0, -1));
  }, [saveBoth, userStars]);

  const removeUserStarById = useCallback(
    async (starId: string) => {
      const next = userStars.filter((star) => star.id !== starId);
      if (next.length === userStars.length) {
        return;
      }
      await saveBoth(next);
    },
    [saveBoth, userStars],
  );

  const resetUserStars = useCallback(async () => {
    await saveBoth([]);
  }, [saveBoth]);

  const updateUserStarById = useCallback(
    async (starId: string, updates: Partial<Pick<UserStar, "label" | "linkedManifestPath" | "size" | "x" | "y">>) => {
      const current = userStarsRef.current;
      let changed = false;
      const next = current.map((star) => {
        if (star.id !== starId) {
          return star;
        }
        changed = true;
        return normalizeUserStar({
          ...star,
          ...updates,
          id: star.id,
          createdAt: star.createdAt,
        });
      });
      if (!changed) {
        return false;
      }
      await saveBoth(next);
      return true;
    },
    [saveBoth],
  );

  return {
    userStars,
    syncError,
    addUserStar,
    addUserStars,
    removeLastUserStar,
    removeUserStarById,
    resetUserStars,
    updateUserStarById,
    starLimit: CONSTELLATION_USER_STAR_LIMIT,
  };
}
