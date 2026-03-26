/**
 * Brain graph animation utilities – Framer Motion enhanced effect compositions
 * for knowledge graph traversal, evidence highlighting, and research narratives.
 */

import { type TargetAndTransition, type Transition, type Variants } from "motion";

/**
 * Smooth evidence panel appearance with staggered content reveal
 */
export const evidencePanelVariants: Variants = {
  hidden: {
    opacity: 0,
    y: 10,
    scale: 0.95,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 15,
      duration: 0.4,
    },
  },
  highlighted: {
    boxShadow: "0 0 24px rgba(168, 85, 247, 0.4)",
    scale: 1.02,
    transition: {
      duration: 0.3,
    },
  },
  exit: {
    opacity: 0,
    y: -10,
    scale: 0.95,
    transition: {
      duration: 0.2,
    },
  },
};

/**
 * Sub-query cascade animation – staggered reveal of research branches
 */
export const subQueryVariants: Variants = {
  hidden: {
    opacity: 0,
    x: -20,
  },
  visible: {
    opacity: 1,
    x: 0,
    transition: {
      type: "spring",
      stiffness: 80,
      damping: 20,
    },
  },
  processing: {
    opacity: 0.7,
    x: 5,
    transition: {
      duration: 0.6,
      repeat: Infinity,
      repeatType: "reverse",
    },
  },
};

/**
 * Knowledge graph node pulse on reveal
 */
export const nodeRevealVariants: Variants = {
  hidden: {
    scale: 0.8,
    opacity: 0,
  },
  visible: {
    scale: 1,
    opacity: 1,
    transition: {
      duration: 0.5,
      ease: "easeOut",
    },
  },
  pulse: {
    scale: [1, 1.05, 1],
    opacity: [1, 0.9, 1],
    transition: {
      duration: 0.6,
      repeat: Infinity,
      repeatType: "loop",
    },
  },
};

/**
 * Connection flash animation between nodes
 */
export const connectionFlashVariants: Variants = {
  initial: {
    opacity: 1,
    strokeDashoffset: 0,
  },
  animate: {
    opacity: 0,
    transition: {
      duration: 0.8,
      ease: "easeInOut",
    },
  },
};

/**
 * Citation highlight animation – draw attention to source material
 */
export const citationHighlightVariants: Variants = {
  rest: {
    borderColor: "rgba(255, 255, 255, 0.1)",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
  },
  highlight: {
    borderColor: "rgba(59, 130, 246, 0.5)",
    backgroundColor: "rgba(59, 130, 246, 0.1)",
    boxShadow: "inset 0 0 12px rgba(59, 130, 246, 0.2)",
    transition: {
      duration: 0.3,
    },
  },
};

/**
 * Research mode expansion ring animation
 */
export const expansionRingVariants: Variants = {
  initial: {
    scale: 0.5,
    opacity: 0.8,
  },
  animate: {
    scale: 2,
    opacity: 0,
    transition: {
      duration: 1.2,
      ease: "easeOut",
    },
  },
};

/**
 * Stagger configuration for cascading animations
 */
export const staggerConfig = {
  evidence: {
    delayChildren: 0.15,
    staggerChildren: 0.08,
  },
  subQueries: {
    delayChildren: 0.1,
    staggerChildren: 0.12,
  },
  nodeReveals: {
    delayChildren: 0.05,
    staggerChildren: 0.06,
  },
};

/**
 * Fast transition for immediate UI feedback
 */
export const fastTransition: Transition = {
  type: "tween",
  duration: 0.15,
  ease: "easeInOut",
};

/**
 * Standard transition for normal interactions
 */
export const standardTransition: Transition = {
  type: "spring",
  stiffness: 100,
  damping: 15,
};

/**
 * Smooth transition for narrative content reveals
 */
export const narrativeTransition: Transition = {
  type: "tween",
  duration: 0.6,
  ease: [0.25, 0.46, 0.45, 0.94], // smooth easeInOutQuad
};

/**
 * Compose multiple animation effects for complex interactions
 */
export function composeAnimationEffects(...effects: Array<TargetAndTransition | null | undefined>) {
  return effects.filter(Boolean).reduce(
    (acc, effect) => ({
      ...acc,
      ...effect,
    }),
    {},
  );
}

/**
 * Create a pulsing effect for loader states
 */
export function createPulseAnimation(intensity = 0.3) {
  return {
    opacity: [1, 1 - intensity, 1],
    transition: {
      duration: 2,
      repeat: Infinity,
      repeatType: "loop" as const,
    },
  };
}

/**
 * Create a shimmer effect for loading skeleton content
 */
export const shimmerVariants: Variants = {
  animate: {
    backgroundPosition: ["200% 0", "-200% 0"],
    transition: {
      duration: 2,
      repeat: Infinity,
      repeatType: "loop" as const,
      ease: "linear",
    },
  },
};
