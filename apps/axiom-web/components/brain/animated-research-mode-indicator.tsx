"use client";

/**
 * AnimatedResearchModeIndicator – displays research progress with animated
 * sub-query cascades and iterative refinement feedback.
 */

import { motion, AnimatePresence } from "motion/react";
import {
  subQueryVariants,
  staggerConfig,
  expansionRingVariants,
} from "@/lib/brain-animation-utils";

export interface SubQuery {
  id: string;
  text: string;
  status: "pending" | "processing" | "complete";
  confidence?: number;
}

export interface AnimatedResearchModeIndicatorProps {
  iteration: number;
  maxIterations: number;
  subQueries: SubQuery[];
  isExpanding?: boolean;
  onSubQueryClick?: (id: string) => void;
  className?: string;
}

export function AnimatedResearchModeIndicator({
  iteration,
  maxIterations,
  subQueries,
  isExpanding = false,
  onSubQueryClick,
  className = "",
}: AnimatedResearchModeIndicatorProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3 }}
      className={`rounded-xl border border-amber-500/30 bg-amber-500/10 backdrop-blur-md ${className}`}
    >
      {/* Expansion rings during active research */}
      <AnimatePresence>
        {isExpanding && (
          <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-xl">
            {[0, 1, 2].map((ring) => (
              <motion.div
                key={`expansion-ring-${ring}`}
                className="absolute inset-0 rounded-full border border-yellow-400/30"
                variants={expansionRingVariants}
                initial="initial"
                animate="animate"
                style={{
                  left: "50%",
                  top: "50%",
                  translateX: "-50%",
                  translateY: "-50%",
                }}
              />
            ))}
          </div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="relative flex items-center justify-between border-b border-amber-500/20 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <motion.div
            className="size-2 rounded-full bg-amber-400"
            animate={{
              scale: isExpanding ? [1, 1.2, 1] : 1,
              opacity: isExpanding ? [1, 0.7, 1] : 1,
            }}
            transition={{
              duration: isExpanding ? 1.5 : 0,
              repeat: isExpanding ? Infinity : 0,
            }}
          />
          <div>
            <h3 className="text-sm font-semibold text-amber-100">Research in Progress</h3>
            <p className="text-xs text-amber-200/60">
              Iteration {iteration} of {maxIterations}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <motion.div
          className="h-1 w-32 rounded-full bg-amber-500/20 overflow-hidden"
          layout
        >
          <motion.div
            className="h-full bg-gradient-to-r from-amber-400 to-amber-500"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: iteration / maxIterations }}
            transition={{ type: "spring", stiffness: 60, damping: 15 }}
            style={{ transformOrigin: "left" }}
          />
        </motion.div>
      </div>

      {/* Sub-queries */}
      {subQueries.length > 0 && (
        <motion.div
          className="space-y-2 px-4 py-3"
          initial="hidden"
          animate="visible"
          variants={{
            visible: {
              transition: {
                staggerChildren: staggerConfig.subQueries.staggerChildren,
                delayChildren: staggerConfig.subQueries.delayChildren,
              },
            },
          }}
        >
          <p className="text-xs font-medium text-amber-200/70 uppercase tracking-wide">
            Active Queries
          </p>

          <div className="space-y-1.5">
            <AnimatePresence mode="popLayout">
              {subQueries.map((sq) => (
                <motion.button
                  key={sq.id}
                  layoutId={`subquery-${sq.id}`}
                  variants={subQueryVariants}
                  initial="hidden"
                  animate={sq.status === "processing" ? "processing" : "visible"}
                  exit="hidden"
                  whileHover={{ paddingLeft: 12 }}
                  onClick={() => onSubQueryClick?.(sq.id)}
                  className="w-full text-left"
                >
                  <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 transition-colors hover:bg-amber-500/10">
                    {/* Status indicator */}
                    <motion.div
                      className="flex-shrink-0"
                      animate={
                        sq.status === "processing"
                          ? { rotate: 360 }
                          : { rotate: 0 }
                      }
                      transition={
                        sq.status === "processing"
                          ? {
                              duration: 2,
                              repeat: Infinity,
                              ease: "linear",
                            }
                          : { duration: 0 }
                      }
                    >
                      {sq.status === "pending" && (
                        <div className="size-2 rounded-full bg-amber-300/40" />
                      )}
                      {sq.status === "processing" && (
                        <div className="size-2 rounded-full bg-amber-400" />
                      )}
                      {sq.status === "complete" && (
                        <motion.svg
                          className="size-4 text-amber-300"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={2}
                          initial={{ scale: 0 }}
                          animate={{ scale: 1 }}
                          transition={{ type: "spring", stiffness: 200, damping: 15 }}
                        >
                          <polyline points="20 6 9 17 4 12" />
                        </motion.svg>
                      )}
                    </motion.div>

                    {/* Query text */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-amber-100 truncate">
                        {sq.text}
                      </p>
                    </div>

                    {/* Confidence score for complete items */}
                    {sq.status === "complete" && sq.confidence != null && (
                      <motion.span
                        className="flex-shrink-0 text-[10px] font-medium text-amber-200/70"
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: 0.3 }}
                      >
                        {Math.round(sq.confidence * 100)}%
                      </motion.span>
                    )}
                  </div>
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

export default AnimatedResearchModeIndicator;
