"use client";

import { useEffect, useState } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

type AnimatedLucideIconMode = "idlePulse" | "spin" | "hoverLift";

export interface AnimatedLucideIconProps extends LucideProps {
  icon: LucideIcon;
  mode?: AnimatedLucideIconMode;
  active?: boolean;
}

export function AnimatedLucideIcon({
  icon: Icon,
  mode = "hoverLift",
  active = true,
  ...iconProps
}: AnimatedLucideIconProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const reduceMotion = useReducedMotion();

  if (!mounted || reduceMotion || !active) {
    return <Icon {...iconProps} />;
  }

  if (mode === "spin") {
    return (
      <motion.span
        className="inline-flex items-center justify-center"
        animate={{ rotate: 360 }}
        transition={{ repeat: Number.POSITIVE_INFINITY, duration: 1.2, ease: "linear" }}
      >
        <Icon {...iconProps} />
      </motion.span>
    );
  }

  if (mode === "idlePulse") {
    return (
      <motion.span
        className="inline-flex items-center justify-center"
        animate={{ scale: [1, 1.08, 1], opacity: [0.9, 1, 0.9] }}
        transition={{ repeat: Number.POSITIVE_INFINITY, duration: 1.8, ease: "easeInOut" }}
      >
        <Icon {...iconProps} />
      </motion.span>
    );
  }

  return (
    <motion.span
      className="inline-flex items-center justify-center"
      whileHover={{ y: -1, rotate: -6, scale: 1.06 }}
      transition={{ type: "spring", stiffness: 340, damping: 20, mass: 0.35 }}
    >
      <Icon {...iconProps} />
    </motion.span>
  );
}
