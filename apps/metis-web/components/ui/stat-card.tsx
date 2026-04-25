"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { BorderBeam } from "@/components/ui/border-beam";
import { cn } from "@/lib/utils";

interface StatCardProps {
  icon?: ReactNode;
  label: string;
  value: string | number;
  detail?: string;
  className?: string;
  beam?: boolean;
}

function isNumericValue(value: string | number): value is number {
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  const parsed = Number(value.replace(/,/g, "").trim());
  return Number.isFinite(parsed);
}

function AnimatedValue({ value }: { value: string | number }) {
  const target = isNumericValue(value) ? Number(value) : null;
  const count = useMotionValue(0);
  const rounded = useTransform(count, (latest) => Math.round(latest));
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (target === null) {
      return;
    }
    const controls = animate(count, target, {
      duration: 0.9,
      ease: "easeOut",
    });
    return () => controls.stop();
  }, [count, target]);

  if (target === null) {
    return (
      <motion.span
        initial={reducedMotion ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24, ease: "easeOut" }}
      >
        {value}
      </motion.span>
    );
  }

  return <motion.span>{rounded}</motion.span>;
}

export function StatCard({ icon, label, value, detail, className, beam = false }: StatCardProps) {
  const body = (
    <div className={cn("glass-panel rounded-2xl p-4", className)}>
      <div className="flex items-center gap-3">
        {icon && (
          <div className="flex size-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
            {icon}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-0.5 text-xl font-semibold tabular-nums text-foreground">
            <AnimatedValue value={value} />
          </p>
        </div>
      </div>
      {detail && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      )}
    </div>
  );

  if (!beam) {
    return body;
  }

  return (
    <BorderBeam size="md" colorVariant="mono" strength={0.6}>
      {body}
    </BorderBeam>
  );
}
