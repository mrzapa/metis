"use client";

/**
 * BrainGraphAnimatedWrapper – wraps BrainGraph3D with Framer Motion animations
 * for smooth transitions, evidence highlighting, and research mode narrative flow.
 *
 * Provides:
 * - Smooth container fade-in on mount
 * - Query expansion animation for Research mode
 * - Evidence panel slide-in/highlight animations
 * - Sub-query cascade animations
 * - Hover state feedback with subtle scale transitions
 */

import { motion, AnimatePresence } from "motion/react";
import { stagger } from "motion";
import { ReactNode } from "react";
import BrainGraph3D, { type BrainGraph3DProps } from "./brain-graph-3d";

export interface BrainGraphAnimatedWrapperProps extends BrainGraph3DProps {
  isResearchMode?: boolean;
  isExpanding?: boolean;
  evidenceCount?: number;
  children?: ReactNode;
}

export function BrainGraphAnimatedWrapper({
  isResearchMode = false,
  isExpanding = false,
  evidenceCount = 0,
  children,
  ...brainGraphProps
}: BrainGraphAnimatedWrapperProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="relative h-full w-full"
    >
      {/* Brain graph with slight scale-in animation */}
      <motion.div
        initial={{ scale: 0.98, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{
          duration: 0.5,
          ease: "easeOut",
          delay: 0.1,
        }}
        className="h-full w-full"
      >
        <BrainGraph3D {...brainGraphProps} />
      </motion.div>

      {/* Research mode indicator with pulse animation */}
      <AnimatePresence>
        {isResearchMode && (
          <motion.div
            key="research-mode-indicator"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="absolute left-5 top-5 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 backdrop-blur-sm"
          >
            <motion.div
              className="size-1.5 rounded-full bg-amber-400"
              animate={{ scale: [1, 1.3, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="text-xs font-medium text-amber-300">Research mode</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Query expansion cascade animation */}
      <AnimatePresence>
        {isExpanding && (
          <motion.div
            key="query-expanding"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
          >
            {/* Expanding query rings */}
            {[0, 1, 2].map((ring) => (
              <motion.div
                key={`ring-${ring}`}
                className="absolute rounded-full border border-purple-400/40"
                initial={{
                  width: 40,
                  height: 40,
                  opacity: 0.6,
                }}
                animate={{
                  width: [40, 200, 400][ring],
                  height: [40, 200, 400][ring],
                  opacity: 0,
                }}
                transition={{
                  duration: 2,
                  delay: ring * 0.3,
                  ease: "easeOut",
                  repeat: isExpanding ? 0 : Infinity,
                  repeatDelay: 2,
                }}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Evidence panel cascade animations */}
      {evidenceCount > 0 && (
        <motion.div
          className="absolute bottom-4 right-4 space-y-2"
          initial="hidden"
          animate="visible"
          variants={{
            visible: {
              transition: {
                staggerChildren: 0.1,
                delayChildren: 0.2,
              },
            },
          }}
        >
          {Array.from({ length: Math.min(evidenceCount, 3) }).map((_, idx) => (
            <motion.div
              key={`evidence-${idx}`}
              variants={{
                hidden: {
                  opacity: 0,
                  x: 20,
                },
                visible: {
                  opacity: 1,
                  x: 0,
                  transition: {
                    type: "spring",
                    stiffness: 100,
                    damping: 15,
                  },
                },
              }}
              className="h-20 w-48 rounded-lg border border-white/20 bg-white/8 p-3 backdrop-blur-md"
            >
              <div className="h-full w-full bg-gradient-to-br from-white/20 to-transparent rounded" />
            </motion.div>
          ))}
        </motion.div>
      )}

      {children}
    </motion.div>
  );
}

export default BrainGraphAnimatedWrapper;
