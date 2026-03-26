"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <motion.div
      className={cn("flex flex-col items-center justify-center py-16 px-6 text-center", className)}
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: {
          transition: {
            staggerChildren: 0.08,
          },
        },
      }}
    >
      {icon && (
        <motion.div
          className="mb-4 flex size-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary"
          variants={{
            hidden: { opacity: 0, y: 8 },
            show: { opacity: 1, y: 0 },
          }}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          {icon}
        </motion.div>
      )}
      <motion.h3
        className="text-lg font-semibold text-foreground"
        variants={{
          hidden: { opacity: 0, y: 8 },
          show: { opacity: 1, y: 0 },
        }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        {title}
      </motion.h3>
      <motion.p
        className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground"
        variants={{
          hidden: { opacity: 0, y: 8 },
          show: { opacity: 1, y: 0 },
        }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        {description}
      </motion.p>
      {action && (
        <motion.div
          className="mt-6"
          variants={{
            hidden: { opacity: 0, y: 8 },
            show: { opacity: 1, y: 0 },
          }}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          {action}
        </motion.div>
      )}
    </motion.div>
  );
}
