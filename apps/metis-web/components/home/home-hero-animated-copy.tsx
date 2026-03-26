"use client";

import { BlurText } from "@/components/vendor/react-bits/text/blur-text";
import { ShinyText } from "@/components/vendor/react-bits/text/shiny-text";

const HERO_HEADLINE = "Local-first intelligence for every document orbit.";
const HERO_SUBLINE = "Grounded retrieval. Quietly animated clarity.";

export function HomeHeroAnimatedCopy() {
  return (
    <div
      data-testid="home-hero-animated-copy"
      className="mt-6 flex flex-col items-center gap-2 px-4 text-center"
    >
      <BlurText
        text={HERO_HEADLINE}
        animateBy="words"
        delay={90}
        stepDuration={0.3}
        className="max-w-136 font-display text-sm uppercase tracking-[0.2em] text-[#c7d8ff]/85 sm:text-base"
      />
      <ShinyText
        text={HERO_SUBLINE}
        speed={2.6}
        delay={0.4}
        color="rgba(184, 199, 233, 0.62)"
        shineColor="#f5f9ff"
        className="text-[11px] uppercase tracking-[0.24em] text-[#b8c7e9]/70 sm:text-xs"
      />
    </div>
  );
}
