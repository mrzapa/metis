"use client";

/**
 * AnimatedEvidencePanel – enhanced evidence display with Framer Motion animations
 * for smoother reveals, highlights, and interactive feedback during research mode.
 */

import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { ReactNode } from "react";
import {
  evidencePanelVariants,
  citationHighlightVariants,
  staggerConfig,
  standardTransition,
} from "@/lib/brain-animation-utils";

export interface EvidenceItem {
  id: string;
  source: string;
  citation: string;
  confidence: number;
  excerpt?: string;
}

export interface AnimatedEvidencePanelProps {
  items: EvidenceItem[];
  isHighlighted?: string | null;
  onItemClick?: (item: EvidenceItem) => void;
  onItemHover?: (id: string | null) => void;
  title?: ReactNode;
  className?: string;
}

export function AnimatedEvidencePanel({
  items,
  isHighlighted,
  onItemClick,
  onItemHover,
  title = "Evidence",
  className = "",
}: AnimatedEvidencePanelProps) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      className={`rounded-lg border border-white/20 bg-white/8 backdrop-blur-md ${className}`}
      initial={reducedMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={standardTransition}
    >
      {/* Header */}
      <div className="border-b border-white/10 px-4 py-3">
        <h3 className="text-sm font-semibold text-white/90">{title}</h3>
        <p className="mt-1 text-xs text-white/50">
          {items.length} source{items.length !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Evidence items */}
      <motion.div
        className="space-y-2 p-4"
        initial="hidden"
        animate="visible"
        variants={{
          visible: {
            transition: {
              staggerChildren: staggerConfig.evidence.staggerChildren,
              delayChildren: staggerConfig.evidence.delayChildren,
            },
          },
        }}
      >
        <AnimatePresence>
          {items.map((item) => (
            <motion.button
              key={item.id}
              layoutId={`evidence-${item.id}`}
              variants={evidencePanelVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onItemClick?.(item)}
              onMouseEnter={() => onItemHover?.(item.id)}
              onMouseLeave={() => onItemHover?.(null)}
              className="w-full text-left"
            >
              <motion.div
                variants={citationHighlightVariants}
                initial="rest"
                animate={isHighlighted === item.id ? "highlight" : "rest"}
                className="rounded-lg border px-3 py-2.5 transition-colors"
              >
                {/* Confidence bar */}
                <motion.div
                  className="absolute inset-0 rounded-lg bg-blue-500/20"
                  initial={reducedMotion ? false : { scaleX: 0 }}
                  animate={{ scaleX: item.confidence }}
                  transition={{ duration: 0.5, delay: 0.1 }}
                  style={{ transformOrigin: "left", zIndex: -1 }}
                />

                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-xs font-medium text-white/90 line-clamp-2">
                      {item.citation}
                    </p>
                    <p className="mt-1 text-[11px] text-white/60">{item.source}</p>
                  </div>
                  <motion.div
                    className="mt-0.5 flex-shrink-0"
                    initial={reducedMotion ? false : { scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ duration: 0.3, delay: 0.1 }}
                  >
                    <span className="inline-block rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/70">
                      {Math.round(item.confidence * 100)}%
                    </span>
                  </motion.div>
                </div>

                {item.excerpt && (
                  <motion.p
                    className="mt-2 text-[11px] text-white/50 line-clamp-2"
                    initial={reducedMotion ? false : { opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2, delay: 0.05 }}
                  >
                    {item.excerpt}
                  </motion.p>
                )}
              </motion.div>
            </motion.button>
          ))}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

export default AnimatedEvidencePanel;
