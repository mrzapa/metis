/**
 * Animation system types and interfaces
 * Provides type safety across all brain graph animation components
 */

import type { TargetAndTransition, Transition, Variants } from "motion";

/**
 * Evidence item for display in evidence panels
 */
export interface EvidenceItem {
  /** Unique identifier */
  id: string;
  /** Source document or reference */
  source: string;
  /** The citation text to display */
  citation: string;
  /** Confidence score 0-1 */
  confidence: number;
  /** Optional excerpt or preview text */
  excerpt?: string;
  /** Optional URL for more info */
  url?: string;
  /** Optional tag for categorization */
  tag?: string;
}

/**
 * Sub-query in research mode
 */
export interface SubQuery {
  /** Unique identifier */
  id: string;
  /** Query text to display */
  text: string;
  /** Current status */
  status: "pending" | "processing" | "complete";
  /** Confidence score when complete (0-1) */
  confidence?: number;
  /** Optional results count */
  resultCount?: number;
  /** Optional error message if failed */
  error?: string;
}

/**
 * Stagger configuration for cascading animations
 */
export interface StaggerConfig {
  /** Delay before children start animating (ms) */
  delayChildren: number;
  /** Delay between each child animation (ms) */
  staggerChildren: number;
}

/**
 * Animation effect composition result
 */
export interface ComposedAnimationEffect extends TargetAndTransition {
  /** Combined animation properties */
  [key: string]: unknown;
}

/**
 * Research mode state
 */
export interface ResearchState {
  /** Whether research mode is active */
  isActive: boolean;
  /** Current iteration number */
  iteration: number;
  /** Maximum iterations */
  maxIterations: number;
  /** Active sub-queries */
  subQueries: SubQuery[];
  /** Currently expanding */
  isExpanding: boolean;
  /** Collected evidence */
  evidence: EvidenceItem[];
}

/**
 * Evidence panel props
 */
export interface EvidencePanelProps {
  /** Evidence items to display */
  items: EvidenceItem[];
  /** Currently highlighted item ID */
  isHighlighted?: string | null;
  /** Callback when item is clicked */
  onItemClick?: (item: EvidenceItem) => void;
  /** Callback when item is hovered */
  onItemHover?: (id: string | null) => void;
  /** Panel title */
  title?: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Research mode indicator props
 */
export interface ResearchModeIndicatorProps {
  /** Current iteration number */
  iteration: number;
  /** Maximum iterations */
  maxIterations: number;
  /** Sub-queries to display */
  subQueries: SubQuery[];
  /** Whether rings are expanding */
  isExpanding?: boolean;
  /** Callback when sub-query is clicked */
  onSubQueryClick?: (id: string) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Numeric animation result
 */
export interface NumericAnimationValue {
  /** The current animated value */
  current: number;
  /** The target value */
  target: number;
  /** Progress 0-1 */
  progress: number;
}

/**
 * Evidence highlight hook return
 */
export interface EvidenceHighlightResult {
  /** Ref to attach to DOM element */
  ref: React.RefObject<HTMLElement>;
  /** Whether element is visible in viewport */
  isVisible: boolean;
}

/**
 * Sub-query animation manager
 */
export interface SubQueryAnimationManager {
  /** Schedule an animation callback */
  scheduleAnimation: (
    id: string,
    delay: number,
    callback: () => void,
  ) => void;
  /** Cancel a scheduled animation */
  cancelAnimation?: (id: string) => void;
  /** Clear all scheduled animations */
  clearAll?: () => void;
}

/**
 * Animation performance metrics
 */
export interface AnimationMetrics {
  /** Average frame rate */
  averageFps: number;
  /** Peak memory usage (MB) */
  peakMemory: number;
  /** Total animation duration (ms) */
  totalDuration: number;
  /** Number of active animations */
  activeAnimations: number;
}

/**
 * Transition configuration
 */
export type TransitionConfig = Transition & {
  /** Type of transition: 'tween' or 'spring' */
  type?: "tween" | "spring";
  /** Duration in milliseconds (for tween) */
  duration?: number;
  /** Easing function or preset */
  ease?: string | number[];
  /** Spring stiffness (for spring) */
  stiffness?: number;
  /** Spring damping (for spring) */
  damping?: number;
  /** Mass for spring physics */
  mass?: number;
};

/**
 * Animation variant definition
 */
export type AnimationVariant = Variants & {
  [key: string]: TargetAndTransition | { transition?: TransitionConfig };
};

/**
 * Brain graph animation wrapper props
 */
export interface BrainGraphAnimationWrapperProps {
  /** Whether research mode is active */
  isResearchMode?: boolean;
  /** Whether query is expanding */
  isExpanding?: boolean;
  /** Number of evidence items to cascade */
  evidenceCount?: number;
  /** Additional children to render */
  children?: React.ReactNode;
}

/**
 * Animation configuration
 */
export interface AnimationConfig {
  /** Enable/disable animations globally */
  enabled: boolean;
  /** Animation duration scale (1.0 = normal, 0.5 = half speed) */
  durationScale: number;
  /** Respect prefers-reduced-motion setting */
  respectReducedMotion: boolean;
  /** GPU prefetch for performance */
  gpuAccelerate: boolean;
  /** Maximum stagger delay to prevent jank */
  maxStaggerDelay: number;
}

/**
 * Research event emitted during animations
 */
export interface ResearchAnimationEvent {
  /** Event type */
  type:
    | "research-started"
    | "query-expanded"
    | "sub-query-complete"
    | "evidence-received"
    | "research-complete";
  /** Event timestamp */
  timestamp: number;
  /** Associated data */
  data?: Record<string, unknown>;
}

/**
 * Animation state machine state
 */
export type AnimationState =
  | "idle"
  | "entering"
  | "active"
  | "processing"
  | "exiting"
  | "error";

/**
 * State transition callback
 */
export type AnimationStateTransition = (
  from: AnimationState,
  to: AnimationState,
) => void;

/**
 * Easing curve configuration
 */
export interface EasingCurve {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * Pre-defined easing curves
 */
export const EASING_CURVES = {
  easeInOutQuad: [0.25, 0.46, 0.45, 0.94],
  easeInOutCubic: [0.645, 0.045, 0.355, 1.0],
  easeInOutQuart: [0.77, 0, 0.175, 1],
  easeInOutQuint: [0.86, 0, 0.07, 1],
  easeInOutExpo: [1, 0, 0, 1],
  easeInOutCirc: [0.785, 0.135, 0.15, 0.86],
} as const;

/**
 * Animation presets
 */
export const ANIMATION_PRESETS = {
  subtle: {
    durationScale: 0.5,
    maxStaggerDelay: 50,
  },
  normal: {
    durationScale: 1.0,
    maxStaggerDelay: 100,
  },
  prominent: {
    durationScale: 1.5,
    maxStaggerDelay: 150,
  },
} as const;
