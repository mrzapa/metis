# Brain Graph Animation System

## Overview

The brain graph animation system enhances METIS's visualization with smooth, performant Framer Motion animations for knowledge graph traversal, evidence highlighting, and research mode narratives.

## Components

### 1. **BrainGraphAnimatedWrapper** (`brain-graph-animated-wrapper.tsx`)
Wraps the 3D brain graph with container animations:
- Smooth fade-in on mount with scale transition
- Research mode indicator with pulsing dot
- Query expansion rings for sub-query visualization
- Staggered evidence panel reveals

**Usage:**
```tsx
import { BrainGraphAnimatedWrapper } from "@/components/brain/brain-graph-animated-wrapper";

<BrainGraphAnimatedWrapper
  data={graphData}
  isResearchMode={true}
  isExpanding={isQueryExpanding}
  evidenceCount={3}
/>
```

### 2. **AnimatedEvidencePanel** (`animated-evidence-panel.tsx`)
Displays evidence with Framer Motion animations:
- Staggered item reveals with spring physics
- Confidence score bars with animated fills
- Citation highlighting on hover/select
- Smooth excerpt expansion
- Click and hover callbacks for interactivity

**Usage:**
```tsx
import { AnimatedEvidencePanel } from "@/components/brain/animated-evidence-panel";

<AnimatedEvidencePanel
  items={evidenceItems}
  isHighlighted={selectedId}
  onItemClick={handleEvidenceClick}
  title="Supporting Evidence"
/>
```

### 3. **AnimatedResearchModeIndicator** (`animated-research-mode-indicator.tsx`)
Shows research progress with sub-query cascades:
- Iteration counter with progress bar
- Sub-query status tracking (pending/processing/complete)
- Expansion rings during active research
- Animated status indicators with proper state transitions
- Confidence scores for completed queries

**Usage:**
```tsx
import { AnimatedResearchModeIndicator } from "@/components/brain/animated-research-mode-indicator";

<AnimatedResearchModeIndicator
  iteration={1}
  maxIterations={3}
  subQueries={[
    { id: "1", text: "Find related topics", status: "processing" },
    { id: "2", text: "Expand context", status: "complete", confidence: 0.92 }
  ]}
  isExpanding={true}
/>
```

## Utilities

### Animation Variants (`lib/brain-animation-utils.ts`)
Pre-configured Framer Motion variants for common patterns:

- **evidencePanelVariants** - Smooth panel reveals with highlights
- **subQueryVariants** - Sub-query slides and processing states
- **nodeRevealVariants** - Graph node appears with pulse options
- **citationHighlightVariants** - Citation border and background highlights
- **expansionRingVariants** - Research mode expansion rings
- **shimmerVariants** - Loading skeleton shimmer effects

### Transitions
- **fastTransition** - Quick UI feedback (150ms)
- **standardTransition** - Normal interactions (spring physics)
- **narrativeTransition** - Smooth content reveals (600ms)

## Custom Hooks

### `useEvidenceHighlight(elementId)`
Tracks when evidence becomes visible via IntersectionObserver
```tsx
const { ref, isVisible } = useEvidenceHighlight("evidence-1");
```

### `useAnimationDebounce(value, delay)`
Debounces animation triggers to prevent spammy state changes
```tsx
const debouncedHover = useAnimationDebounce(hoveredId, 150);
```

### `useSubQueryAnimation(subQueries)`
Manages cascading sub-query animations with cleanup
```tsx
const { scheduleAnimation } = useSubQueryAnimation(subQueries);
```

### `useNumericAnimation(targetValue, duration)`
Smoothly animates numeric values with easing
```tsx
const animatedConfidence = useNumericAnimation(0.92, 1000);
```

### `useResearchExpansion(isExpanding)`
Detects and tracks research mode expansion state
```tsx
const isExpanding = useResearchExpansion(isActive);
```

### `useAnimationThrottle(callback, targetFps)`
Throttles animation callbacks for performance
```tsx
useAnimationThrottle(() => updateAnimation(), 60);
```

## Animation Flows

### Research Mode Initialization
1. Container fades in (0s → 0.6s)
2. Brain graph scales up (0.1s → 0.6s)
3. Research indicator appears (0s → 0.3s)
4. Expansion rings pulse (triggered on query)

### Evidence Reveal
1. Panel slides in from bottom-right with spring
2. Items stagger with 80ms delays
3. Confidence bars fill left-to-right
4. Excerpts expand on demand

### Sub-Query Cascade
1. Initial query enters (50% opacity, -20px offset)
2. Processing queries pulse with 600ms repeat
3. Complete queries show checkmark with scale animation
4. Confidence scores appear with 300ms delay

## Performance Considerations

1. **Stagger delays** - All cascading animations use debounced stagger configs to prevent browser jank
2. **AnimatePresence** - Properly exits animations before unmounting
3. **layoutId** - Shared layout animations for smooth transitions
4. **GPU acceleration** - Uses `transform` and `opacity` for 60fps animations
5. **Throttling** - Resort to `useAnimationThrottle` for high-frequency updates

## Integration Points

### With RAG Query System
- Trigger `isExpanding={true}` when Research mode initiates sub-queries
- Update `subQueries` state with new queries as they generate
- Highlight evidence as it's retrieved via `onItemClick` callbacks

### With Brain Graph 3D
- Sync `selectedNodeId` to highlight evidence from clicked nodes
- Cascade animations when transitioning between graph views
- Use evidence panel as secondary narrative alongside 3D visualization

### With Chat Interface
- Evidence panels integrate into Evidence Pack skill narratives
- Research indicators show iterative refinement progress
- Animations provide feedback during long-running queries

## Future Enhancements

- Connection flash animations when traversing graph edges
- Particle effects for knowledge graph node activation
- Gesture-based animations on mobile (swipe, pinch)
- Audio feedback synchronized with key animation milestones
- Accessibility: Reduced motion support via `prefers-reduced-motion`

## Dependencies

- `motion` (Framer Motion v12.38.0) - Already installed in `metis-web`
- React 19.2.3+

## See Also

- [Brain Graph 3D](./brain-graph-3d.tsx)
- [Brain Graph View Model](./brain-graph-view-model.ts)
- [Animation Utils](../lib/brain-animation-utils.ts)
