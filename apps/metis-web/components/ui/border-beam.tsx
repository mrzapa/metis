"use client";

import { forwardRef, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import {
  BorderBeam as UpstreamBorderBeam,
  type BorderBeamProps as UpstreamBorderBeamProps,
} from "border-beam";
import { cn } from "@/lib/utils";

type MetisBorderBeamProps = Omit<UpstreamBorderBeamProps, "children"> & {
  children: ReactNode;
};

export const BorderBeam = forwardRef<HTMLDivElement, MetisBorderBeamProps>(
  function BorderBeam(
    {
      children,
      className,
      colorVariant = "mono",
      theme = "dark",
      size = "md",
      active,
      ...rest
    },
    ref,
  ) {
    const prefersReducedMotion = useReducedMotion();
    const isActive = active ?? !prefersReducedMotion;

    return (
      <UpstreamBorderBeam
        ref={ref}
        className={cn(className)}
        colorVariant={colorVariant}
        theme={theme}
        size={size}
        active={isActive}
        {...rest}
      >
        {children}
      </UpstreamBorderBeam>
    );
  },
);

export type { BorderBeamColorVariant, BorderBeamSize, BorderBeamTheme } from "border-beam";
