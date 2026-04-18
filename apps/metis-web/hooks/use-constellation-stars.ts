"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSettings, updateSettings, postNourishmentEvent } from "@/lib/api";
import {
  capUserStars,
  CONSTELLATION_USER_STAR_LIMIT,
  getRemainingUserStarSlots,
  type UserStar,
  normalizeUserStar,
  parseUserStars,
} from "@/lib/constellation-types";
import { fnv1a32, SeededRNG, generateClassicalDesignation } from "@/lib/star-catalogue";

/**
 * Legacy procedural fallback for user stars created without an explicit
 * label. ADR 0006 calls for user-supplied names on user-content stars;
 * this helper keeps the current click-to-add UX intact by producing a
 * classical-style designation until the Observatory naming UI lands.
 * Size [0.5, 2.0] maps to magnitude [6, 1] — bigger = brighter.
 */
function makeProceduralStarName(x: number, y: number, now: number, size: number): string {
  const seed = fnv1a32(`${Math.round(x * 10000)},${Math.round(y * 10000)},${now}`);
  const rng = new SeededRNG(seed);
  const magnitude = Math.max(1, 7 - (size * 2.5));
  return generateClassicalDesignation(rng, magnitude);
}

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

function normalizeStarCollection(stars: ReadonlyArray<UserStar>): UserStar[] {
  return stars.map((star) =>
    normalizeUserStar({
      ...star,
      id: star.id,
      createdAt: star.createdAt,
    }),
  );
}

export function useConstellationStars() {
  const [userStars, setUserStars] = useState<UserStar[]>(() => capUserStars(readLocal()));
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

    if (userStarsRef.current.length > 0) {
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

  const saveBoth = useCallback(async (nextStars: ReadonlyArray<UserStar>) => {
    const capped = capUserStars(normalizeStarCollection(nextStars));
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
        return null;
      }
      const now = Date.now();
      const label = star.label?.trim() || makeProceduralStarName(star.x, star.y, now, star.size ?? 1);
      const createdStar = normalizeUserStar({
        ...star,
        label,
        id: `star-${now}-${Math.round(Math.random() * 100000)}`,
        createdAt: now,
      });
      const next = [
        ...current,
        createdStar,
      ];
      await saveBoth(next);
      // Fire-and-forget nourishment event — don't block star interaction
      postNourishmentEvent({
        event_type: "star_added",
        star_id: createdStar.id,
        faculty_id: createdStar.primaryDomainId ?? "",
        detail: createdStar.label ?? "",
      }).catch(() => {/* nourishment event is best-effort */});
      return createdStar;
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
      const nextStars = starsToAdd.map((star, index) => {
        const label = star.label?.trim() || makeProceduralStarName(star.x, star.y, now + index, star.size ?? 1);
        return normalizeUserStar({
          ...star,
          label,
          id: `star-${now}-${index}-${Math.round(Math.random() * 100000)}`,
          createdAt: now + index,
        });
      });
      if (nextStars.length === 0) {
        return 0;
      }

      await saveBoth([...current, ...nextStars]);
      return nextStars.length;
    },
    [saveBoth],
  );

  const removeLastUserStar = useCallback(async () => {
    const current = userStarsRef.current;
    if (current.length === 0) {
      return;
    }
    await saveBoth(current.slice(0, -1));
  }, [saveBoth]);

  const removeUserStarById = useCallback(
    async (starId: string) => {
      const current = userStarsRef.current;
      const next = current
        .filter((star) => star.id !== starId)
        .map((star) => {
          if (!star.connectedUserStarIds?.includes(starId)) {
            return star;
          }
          return normalizeUserStar({
            ...star,
            connectedUserStarIds: star.connectedUserStarIds.filter((linkedStarId) => linkedStarId !== starId),
            id: star.id,
            createdAt: star.createdAt,
          });
        });
      if (next.length === current.length) {
        return;
      }
      await saveBoth(next);
      // Fire-and-forget nourishment event — triggers punishment loop
      const removedStar = current.find((s) => s.id === starId);
      postNourishmentEvent({
        event_type: "star_removed",
        star_id: starId,
        faculty_id: removedStar?.primaryDomainId ?? "",
        detail: removedStar?.label ?? "",
      }).catch(() => {/* nourishment event is best-effort */});
    },
    [saveBoth],
  );

  const resetUserStars = useCallback(async () => {
    await saveBoth([]);
  }, [saveBoth]);

  const replaceUserStars = useCallback(async (nextStars: ReadonlyArray<UserStar>) => {
    await saveBoth(nextStars);
  }, [saveBoth]);

  const updateUserStarById = useCallback(
    async (
      starId: string,
      updates: Partial<
        Pick<
          UserStar,
          | "label"
          | "primaryDomainId"
          | "relatedDomainIds"
          | "stage"
          | "intent"
          | "notes"
          | "connectedUserStarIds"
          | "linkedManifestPaths"
          | "activeManifestPath"
          | "linkedManifestPath"
          | "learningRoute"
          | "size"
          | "x"
          | "y"
        >
      >,
    ) => {
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
    replaceUserStars,
    updateUserStarById,
    starLimit: CONSTELLATION_USER_STAR_LIMIT,
  };
}
