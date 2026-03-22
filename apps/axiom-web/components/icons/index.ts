/**
 * Animated icons from lucide-animated (pqoqubbw/icons).
 *
 * These are animated, hover-interactive replacements for static lucide-react
 * icons.  Each icon accepts a `size` prop and animates on mouse hover.  For
 * programmatic control, obtain a ref and call `startAnimation()`/`stopAnimation()`.
 *
 * Source: https://github.com/pqoqubbw/icons
 *
 * Usage:
 * ```tsx
 * import { BrainIcon } from "@/components/icons";
 * <BrainIcon size={20} className="text-muted-foreground" />
 * ```
 */

export { BotIcon, type BotIconHandle } from "./bot";
export { BrainIcon, type BrainIconHandle } from "./brain";
export { SearchIcon, type SearchIconHandle } from "./search";
export { SendIcon, type SendIconHandle } from "./send";
export { SettingsIcon, type SettingsIconHandle } from "./settings";
