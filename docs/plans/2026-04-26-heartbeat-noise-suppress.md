# Heartbeat Noise Suppression Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop the companion-dock thought log from showing `"Seedling heartbeat"` × 6 to brand-new users by filtering lifecycle-tick events at the activity-bridge boundary while preserving the underlying boot_id replay-detection mechanism.

**Architecture:** The Seedling worker emits a `CompanionActivityEvent` on every tick (`worker.py:125`) for liveness + boot_id tracking. The frontend bridge in `apps/metis-web/lib/api.ts` re-emits it through the `companionActivity` bus. The fix is a one-line guard in the bridge that drops events matching the lifecycle-heartbeat structural signature (`source: "seedling"` + `state: "running"` + `trigger: "lifecycle"`) before they reach `emitCompanionActivity`. All other seedling events (Phase 3 comets, Phase 4 reflections, Phase 5 stage transitions, Phase 6 brain links) flow through unchanged because they carry different state/trigger combinations.

**Tech Stack:** TypeScript, Vitest (frontend tests).

---

### Task 1: Add the failing test that asserts heartbeats are dropped

**Files:**
- Modify: `apps/metis-web/lib/__tests__/api.test.ts:97-136` (the existing `"emits buffered Seedling activity through the companion bus once"` test)

The existing test uses a heartbeat-shaped fixture (`state: "running"`, `trigger: "lifecycle"`, `summary: "Seedling heartbeat"`) to verify the dedup machinery emits it once. After the filter lands, that fixture must be DROPPED. Restructure into two tests: one that asserts the heartbeat is filtered, and one that asserts non-heartbeat seedling events still flow through (preserving the dedup-once assertion on a fixture that survives the filter).

**Step 1: Replace the existing test block at lines 97-136**

Read `apps/metis-web/lib/__tests__/api.test.ts` lines 97-136. Replace with:

```typescript
  it("filters lifecycle heartbeat events from the companion bus", async () => {
    // Phase 2's tick emits ``state: "running"`` / ``trigger: "lifecycle"``
    // with summary "Seedling heartbeat" every cycle for boot_id tracking.
    // These are not user-facing — the dock's sigil-pulse already skips
    // them, and the thought log should too. Filter at the bridge so
    // every subscriber inherits the rule.
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    const payload = {
      running: true,
      last_tick_at: "2026-04-24T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-24T20:01:00+00:00",
      queue_depth: 0,
      activity_events: [
        {
          source: "seedling",
          state: "running",
          trigger: "lifecycle",
          summary: "Seedling heartbeat",
          timestamp: 1770000000000,
          payload: { event_id: "seedling-heartbeat-1", boot_id: "test-heartbeat" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    );

    await fetchSeedlingStatus();
    unsubscribe();

    expect(events).toEqual([]);
  });

  it("emits non-heartbeat Seedling activity through the companion bus once", async () => {
    // Real activity (anything not matching the lifecycle-heartbeat
    // signature) must still reach subscribers, and the boot_id dedup
    // machinery must still ensure each event_id only fires once.
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    const payload = {
      running: true,
      last_tick_at: "2026-04-24T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-24T20:01:00+00:00",
      queue_depth: 0,
      activity_events: [
        {
          source: "seedling",
          state: "completed",
          trigger: "comet_absorbed",
          summary: "Absorbed news comet: GPU prices drop",
          timestamp: 1770000000000,
          payload: { event_id: "seedling-real-1", boot_id: "test-emit-once" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    );

    await fetchSeedlingStatus();
    await fetchSeedlingStatus();
    unsubscribe();

    expect(events).toEqual([
      expect.objectContaining({
        source: "seedling",
        state: "completed",
        summary: "Absorbed news comet: GPU prices drop",
      }),
    ]);
  });
```

**Step 2: Run the new tests — both should fail because the filter doesn't exist yet**

Run: `cd apps/metis-web && npx vitest run lib/__tests__/api.test.ts -t "filters lifecycle heartbeat" -t "emits non-heartbeat Seedling activity"`
Expected: First test FAILS (heartbeat reaches the listener; `events` is non-empty). Second test PASSES (the existing flow already handles non-heartbeat events correctly).

**Step 3: Commit the failing-test scaffold**

```bash
git add apps/metis-web/lib/__tests__/api.test.ts
git commit -m "test(m13): heartbeat filter — failing test"
```

---

### Task 2: Update the boot_id replay-detection test fixture

**Files:**
- Modify: `apps/metis-web/lib/__tests__/api.test.ts:138-176` (the `"re-emits replayed sequence numbers when the worker boot_id changes"` test)

This test uses heartbeat-shaped fixtures (`state: "running"`, `trigger: "lifecycle"`) with summaries `"before restart"` / `"after restart"`. After the filter, the events would be dropped because they match the heartbeat signature regardless of summary. Update the fixtures to use `state: "completed"` so the dedup-on-boot-id-change behaviour is still exercised on a survived event shape.

**Step 1: Edit `buildPayload` in the test**

Locate lines 142-160 and change `state: "running"` → `state: "completed"` and `trigger: "lifecycle"` → `trigger: "comet_absorbed"`.

```typescript
function buildPayload(bootId: string, summary: string) {
  return {
    running: true,
    last_tick_at: "2026-04-24T20:00:00+00:00",
    current_stage: "seedling",
    next_action_at: "2026-04-24T20:01:00+00:00",
    queue_depth: 0,
    activity_events: [
      {
        source: "seedling",
        state: "completed",
        trigger: "comet_absorbed",
        summary,
        timestamp: 1770000000000,
        payload: { event_id: `seedling-${bootId}-1`, boot_id: bootId },
      },
    ],
  };
}
```

**Step 2: Run the boot_id test — it should still pass (no filter changes yet, but the fixture is now filter-survivable)**

Run: `cd apps/metis-web && npx vitest run lib/__tests__/api.test.ts -t "re-emits replayed"`
Expected: PASS.

**Step 3: Commit**

```bash
git add apps/metis-web/lib/__tests__/api.test.ts
git commit -m "test(m13): update boot_id replay fixture to non-heartbeat shape"
```

---

### Task 3: Implement the heartbeat filter at the activity bridge

**Files:**
- Modify: `apps/metis-web/lib/api.ts:2780-2803` (inside the `for (const event of activity_events)` loop that re-emits seedling events)

**Step 1: Read the current bridge code**

Read `apps/metis-web/lib/api.ts` lines 2780-2803 to confirm the structure. The relevant block is the loop that calls `emitCompanionActivity({...event, source: "seedling", ...})`.

**Step 2: Add the filter before the emit**

Insert the filter check inside the loop, after the `seenSeedlingActivityEventIds.add(eventId)` line and before `emitCompanionActivity(...)`:

```typescript
    // Drop lifecycle heartbeats. The worker emits one of these every
    // tick (Phase 2's deliberately-no-op heartbeat) for boot_id
    // tracking. They are not user-facing — the dock's sigil-pulse
    // already skips them. Filter here at the single emit point so
    // every subscriber (thought log, unseen-count badge, future
    // listeners) inherits the rule.
    if (
      event.state === "running" &&
      (event.trigger || "lifecycle") === "lifecycle"
    ) {
      continue;
    }
    emitCompanionActivity({
      ...event,
      source: "seedling",
      state: event.state,
      trigger: event.trigger || "lifecycle",
      summary: event.summary || "Seedling heartbeat",
    });
```

The `(event.trigger || "lifecycle") === "lifecycle"` check mirrors the trigger-default that the bridge already applies on the next line — events without an explicit trigger ARE lifecycle ticks by definition.

**Step 3: Run the filter test — should now pass**

Run: `cd apps/metis-web && npx vitest run lib/__tests__/api.test.ts -t "filters lifecycle heartbeat"`
Expected: PASS.

**Step 4: Run the full api.test.ts suite — everything should still pass**

Run: `cd apps/metis-web && npx vitest run lib/__tests__/api.test.ts`
Expected: All tests pass (heartbeat filter, non-heartbeat dedup, boot_id replay, forecast helpers).

**Step 5: Commit**

```bash
git add apps/metis-web/lib/api.ts
git commit -m "feat(m13): suppress lifecycle heartbeats at activity bridge

Filter ``source: 'seedling'`` events with ``state: 'running'`` and
``trigger: 'lifecycle'`` (the Phase 2 worker tick signature) before
they reach ``emitCompanionActivity``. Closes the new-user audit
finding that the dock's thought log was showing 'Seedling heartbeat'
× 6 to brand-new users.

The dock's sigil-pulse animation already skipped these events
(metis-companion-dock.tsx:319). The thought log just didn't get the
memo. Filtering at the single emit point means every subscriber
(thought log, unseen-count badge, future listeners) inherits the
rule.

Real Seedling activity (Phase 3 comets, Phase 4 reflections, Phase 5
stage transitions, Phase 6 brain links) carries different state /
trigger combinations and flows through unchanged.

Closes plans/seedling-and-feed/plan.md *Next up* item 5."
```

---

### Task 4: Smoke-check the surrounding test suite

**Step 1: Run the full frontend test suite**

Run: `cd apps/metis-web && npx vitest run`
Expected: All passing. The change is a frontend-only one-line guard; nothing else should regress.

**Step 2: Run the full backend test suite (sanity)**

Run: `python -m pytest tests/test_api_seedling.py tests/test_seedling.py -q`
Expected: All passing. Backend is untouched but the Seedling worker still emits the heartbeat — just no one's listening.

**Step 3: Run ruff (sanity, even though no Python changed)**

Run: `python -m ruff check metis_app/seedling/`
Expected: All checks passed.

---

### Task 5: Update the plan doc and IMPLEMENTATION.md

**Files:**
- Modify: `plans/seedling-and-feed/plan.md` *Progress* section (add 2026-04-26 entry) + *Next up* (remove item 5)
- Modify: `plans/seedling-and-feed/plan.md` *Last updated* header
- Modify: `plans/IMPLEMENTATION.md` M13 row claim field

**Step 1: Append a Progress entry for the heartbeat fix**

In `plans/seedling-and-feed/plan.md`, after the most recent Progress entry (currently the Phase 4b limitation note), add:

```markdown
- **2026-04-26 — New-user audit follow-up: heartbeat noise suppressed.**
  ``apps/metis-web/lib/api.ts`` now drops ``source: "seedling"`` events
  matching the lifecycle-heartbeat structural signature
  (``state: "running"`` + ``trigger: "lifecycle"``) before they reach
  ``emitCompanionActivity``. The Phase 2 worker still emits the
  heartbeat for boot_id tracking, but the user-facing thought log no
  longer shows 6 lines of "Seedling heartbeat" to brand-new users.
  The dock's sigil-pulse animation already skipped these events; this
  brings the thought log in line. Real Seedling activity (Phase 3
  comets, Phase 4 reflections, Phase 5 stage transitions, Phase 6
  brain links) carries different state / trigger combinations and is
  unaffected. Closes *Next up* item 5.
```

**Step 2: Remove item 5 from the *Next up* list**

Delete the heartbeat-label item (currently listed as item 5 in *Next up*) and renumber the M13 close-out item.

**Step 3: Bump *Last updated***

Change `Last updated: 2026-04-26 by Claude` (already current — no change needed).

**Step 4: Update IMPLEMENTATION.md M13 row Claim field**

Change `claude/m13-phase7-lora-training-log` → `claude/m13-heartbeat-noise-suppress`.

**Step 5: Commit**

```bash
git add plans/seedling-and-feed/plan.md plans/IMPLEMENTATION.md
git commit -m "docs(m13): record heartbeat-noise-suppress in Progress"
```

---

### Task 6: Push branch and open PR

**Step 1: Push**

```bash
git push -u origin claude/m13-heartbeat-noise-suppress
```

**Step 2: Open PR with gh**

Use `gh pr create` with title `fix(m13): suppress lifecycle heartbeats from companion thought log` and body that:

- States the audit finding it closes (item 5 of *Next up*).
- Notes the fix is a frontend-only one-line bridge filter.
- Notes it's independent of in-flight PRs #558 (Phase 6) and #561 (Phase 7).
- Lists the structural filter rule and why it's preferable to a string-match or missing-summary filter.
- Test plan: 4 vitest cases (filter, non-heartbeat dedup, boot_id replay, forecast helpers) + manual smoke (open the dock as a new user, confirm no "Seedling heartbeat" entries).

---

## Done criteria

1. `cd apps/metis-web && npx vitest run lib/__tests__/api.test.ts` → all green.
2. New-user dock view shows no `"Seedling heartbeat"` lines for 5 minutes of idle (manual smoke check).
3. Real Seedling activity (e.g. trigger an autonomous research run) still appears in the thought log.
4. Plan doc *Next up* no longer lists the heartbeat label as outstanding.
5. PR opened against `main`.
