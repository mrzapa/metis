"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface AmbientBackdropProps {
  className?: string;
  dense?: boolean;
}

export function AmbientBackdrop({ className, dense = false }: AmbientBackdropProps) {
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden="true">
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="absolute inset-0"
      >
        <div className="absolute inset-0 hero-grid" />
        <div className="absolute left-[-12%] top-[-12%] h-[36rem] w-[36rem] rounded-full bg-primary/20 blur-[140px]" />
        <div className="absolute right-[-10%] top-[12%] h-[28rem] w-[28rem] rounded-full bg-chart-2/18 blur-[130px]" />
        <div className="absolute bottom-[-24%] left-[22%] h-[26rem] w-[26rem] rounded-full bg-chart-4/14 blur-[120px]" />
        {!dense && (
          <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-background via-background/85 to-transparent" />
        )}
      </motion.div>
    </div>
  );
}
