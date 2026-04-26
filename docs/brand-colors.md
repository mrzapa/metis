# METIS Brand Colour Scheme

> Extracted from the live METIS UI for the branding team.
> Source of truth: `apps/metis-web/app/tokens.css`,
> `apps/metis-web/components/shell/hud/hud-themes.ts`, and component-level styling.
>
> METIS uses the **OKLCh** colour space for all design tokens (perceptually
> uniform, ideal for accessible contrast tuning). Hex equivalents are
> provided alongside for branding tools that don't speak OKLCh.

---

## 1. Core brand identity

The METIS palette is anchored by a **deep cosmic blue** with a **warm amber-gold** accent — reflecting the "brain graph / constellation" metaphor at the heart of the product.

| Role | OKLCh | Approx. Hex | Notes |
|---|---|---|---|
| **Brand primary (light)** | `oklch(0.57 0.11 214)` | `#3b8fc4` | Cosmic blue, used for CTAs, focus rings, links |
| **Brand primary (dark)** | `oklch(0.72 0.11 205)` | `#5fb8d9` | Brighter blue for dark surfaces |
| **Brand accent — gold** | `oklch(0.72 0.12 78)` | `#d4a443` | Warm amber-gold for brand marks, "assistant" identity |
| **Brand accent — gold muted** | `oklch(0.58 0.08 78)` | `#9c7a36` | Subdued gold for secondary marks |
| **Destructive / error** | `oklch(0.577 0.245 27.325)` | `#c63a2a` | Used sparingly, error states only |

---

## 2. Light-mode tokens

Surface and text tokens for the default (light) theme.
Source: `apps/metis-web/app/tokens.css:1-34`.

| Token | OKLCh | Approx. Hex | Purpose |
|---|---|---|---|
| `--background` | `oklch(0.985 0.01 245)` | `#f8f9fc` | Page background |
| `--foreground` | `oklch(0.22 0.018 248)` | `#2c3038` | Primary text |
| `--card` | `oklch(0.992 0.008 240)` | `#fafbfd` | Card surfaces |
| `--card-foreground` | `oklch(0.2 0.018 248)` | `#282c34` | Text on cards |
| `--popover` | `oklch(0.992 0.008 240)` | `#fafbfd` | Popovers / menus |
| `--popover-foreground` | `oklch(0.2 0.018 248)` | `#282c34` | Text in popovers |
| `--primary` | `oklch(0.57 0.11 214)` | `#3b8fc4` | Primary actions |
| `--primary-foreground` | `oklch(0.98 0.006 250)` | `#f7f8fc` | Text on primary |
| `--secondary` | `oklch(0.95 0.015 235)` | `#eef0f5` | Secondary surfaces |
| `--secondary-foreground` | `oklch(0.28 0.025 244)` | `#3b414c` | Text on secondary |
| `--muted` | `oklch(0.95 0.014 235)` | `#eef0f4` | Muted surfaces |
| `--muted-foreground` | `oklch(0.48 0.03 240)` | `#6a7280` | Muted / placeholder text |
| `--accent` | `oklch(0.9 0.035 205)` | `#d4e3eb` | Light accent surfaces |
| `--accent-foreground` | `oklch(0.27 0.03 244)` | `#3a4150` | Text on accent |
| `--destructive` | `oklch(0.577 0.245 27.325)` | `#c63a2a` | Error / destructive |
| `--border` | `oklch(0.89 0.012 240)` | `#dadee5` | Borders / dividers |
| `--input` | `oklch(0.91 0.014 238)` | `#dee2e9` | Form input backgrounds |
| `--ring` | `oklch(0.67 0.1 214)` | `#5ba1cf` | Focus ring |

### Sidebar (light)
| Token | OKLCh | Purpose |
|---|---|---|
| `--sidebar` | `oklch(0.975 0.008 244)` | Sidebar background |
| `--sidebar-foreground` | `oklch(0.2 0.018 248)` | Sidebar text |
| `--sidebar-primary` | `oklch(0.57 0.11 214)` | Active item |
| `--sidebar-accent` | `oklch(0.92 0.028 208)` | Hover state |
| `--sidebar-border` | `oklch(0.88 0.012 240)` | Divider |
| `--sidebar-ring` | `oklch(0.67 0.1 214)` | Focus ring |

---

## 3. Dark-mode tokens (default theme)

The dark theme is the **flagship aesthetic** — METIS is primarily a dark-mode product evoking deep space.
Source: `apps/metis-web/app/tokens.css:36-70`.

| Token | OKLCh | Approx. Hex | Purpose |
|---|---|---|---|
| `--background` | `oklch(0.09 0.018 248)` | `#0c0f17` | Deep-space background |
| `--foreground` | `oklch(0.95 0.008 235)` | `#ecedf0` | Primary text |
| `--card` | `oklch(0.12 0.018 247)` | `#11151e` | Card surfaces |
| `--card-foreground` | `oklch(0.95 0.008 235)` | `#ecedf0` | Text on cards |
| `--popover` | `oklch(0.11 0.018 248)` | `#0f131c` | Popovers |
| `--popover-foreground` | `oklch(0.95 0.008 235)` | `#ecedf0` | Text in popovers |
| `--primary` | `oklch(0.72 0.11 205)` | `#5fb8d9` | Primary actions |
| `--primary-foreground` | `oklch(0.18 0.02 244)` | `#23272f` | Text on primary |
| `--secondary` | `oklch(0.16 0.018 244)` | `#181c25` | Secondary surfaces |
| `--secondary-foreground` | `oklch(0.93 0.008 235)` | `#e6e7ea` | Text on secondary |
| `--muted` | `oklch(0.15 0.016 244)` | `#161a22` | Muted surfaces |
| `--muted-foreground` | `oklch(0.73 0.02 232)` | `#a3aab5` | Muted text |
| `--accent` | `oklch(0.18 0.024 210)` | `#1d2530` | Accent surfaces |
| `--accent-foreground` | `oklch(0.95 0.008 235)` | `#ecedf0` | Text on accent |
| `--destructive` | `oklch(0.704 0.191 22.216)` | `#e26350` | Error |
| `--border` | `oklch(1 0 0 / 9%)` | `rgba(255,255,255,0.09)` | Borders |
| `--input` | `oklch(1 0 0 / 10%)` | `rgba(255,255,255,0.10)` | Inputs |
| `--ring` | `oklch(0.72 0.11 205)` | `#5fb8d9` | Focus ring |
| `--gold` | `oklch(0.72 0.12 78)` | `#d4a443` | **Brand gold** — assistant identity, marks |
| `--gold-muted` | `oklch(0.58 0.08 78)` | `#9c7a36` | Muted gold |

### Sidebar (dark)
| Token | OKLCh | Purpose |
|---|---|---|
| `--sidebar` | `oklch(0.10 0.018 248)` | Sidebar background |
| `--sidebar-foreground` | `oklch(0.95 0.008 235)` | Sidebar text |
| `--sidebar-primary` | `oklch(0.72 0.11 205)` | Active item |
| `--sidebar-accent` | `oklch(0.28 0.03 205)` | Hover state |
| `--sidebar-border` | `oklch(1 0 0 / 8%)` | Divider |

---

## 4. Data visualisation palette

Five-stop chart palette, designed to remain perceptually distinct in both modes.
Source: `apps/metis-web/app/tokens.css:20-24` (light) and `:55-59` (dark).

| Token | Light OKLCh | Dark OKLCh | Hue family |
|---|---|---|---|
| `--chart-1` | `oklch(0.62 0.11 214)` | `oklch(0.72 0.11 205)` | Blue (primary) |
| `--chart-2` | `oklch(0.65 0.08 191)` | `oklch(0.68 0.09 185)` | Cyan |
| `--chart-3` | `oklch(0.72 0.14 82)` | `oklch(0.76 0.15 82)` | Yellow |
| `--chart-4` | `oklch(0.68 0.12 52)` | `oklch(0.72 0.13 56)` | Orange |
| `--chart-5` | `oklch(0.58 0.08 160)` | `oklch(0.66 0.08 160)` | Teal-green |

---

## 5. HUD (heads-up display) semantic colours

Used in the always-on companion HUD. Most delegate to core tokens; three are HUD-specific.
Source: `apps/metis-web/components/shell/hud/hud-themes.ts:5-14`.

| Token | Value | Purpose |
|---|---|---|
| `--hud-primary` | → `--primary` | Inherits brand blue |
| `--hud-accent` | → `--gold` (fallback `oklch(0.72 0.12 78)`) | Brand gold accent |
| `--hud-text` | → `--foreground` | HUD body text |
| `--hud-text-dim` | → `--muted-foreground` | Dimmed HUD text |
| `--hud-border` | → `--border` | HUD chrome |
| `--hud-success` | `oklch(0.66 0.18 155)` | Green status |
| `--hud-warning` | `oklch(0.72 0.14 65)` | Amber warning |
| `--hud-error` | → `--destructive` | Red error |

---

## 6. Brain-graph node palette

The signature visualisation: each knowledge-node type has a fixed identity colour.
Source: `apps/metis-web/components/brain/brain-graph.tsx:51-73`.

| Node type | Hex | Meaning |
|---|---|---|
| `category` | `#6366f1` | Indigo — knowledge categories |
| `index` | `#0969da` | Blue — indexed content |
| `session` | `#2da44e` | Green — sessions |
| `assistant` | `#e3b341` | **Gold — assistant identity (brand)** |
| `memory` | `#a371f7` | Purple — memory |
| `playbook` | `#db61a2` | Pink — playbooks |

### Brain edge / scope colours
| Scope | RGBA | Meaning |
|---|---|---|
| `workspace` | `rgba(130,180,255,0.28)` | Workspace edges |
| `assistant_self` | `rgba(227,179,65,0.50)` | Gold — assistant's own knowledge |
| `assistant_learned` | `rgba(163,113,247,0.55)` | Purple — learned knowledge |

---

## 7. Activity / event colours

Real-time activity indicators in the companion dock and HUD.
Source: `apps/metis-web/components/shell/metis-companion-dock.tsx:932-937`.

| Event | Hex | Meaning |
|---|---|---|
| `rag_stream` | `#60a5fa` | Bright blue — Q&A / RAG |
| `index_build` | `#4ade80` | Green — index building |
| `autonomous_research` | `#a78bfa` | Purple — autonomous research |
| `reflection` | `#fbbf24` | Amber — reflection |
| `seedling` | `#10b981` | Emerald — seedling growth |
| `news_comet` | `#fb923c` | Orange — news / comet events |

---

## 8. Status pill palette

Connection / health indicators (Tailwind tokens).
Source: `apps/metis-web/components/shell/status-pill.tsx:10-31`.

| Status | Tailwind | Hex (approx.) |
|---|---|---|
| connected | `emerald-400` | `#34d399` |
| checking | `amber-300` | `#fcd34d` |
| disconnected | `rose-400` | `#fb7185` |
| warning | `chart-4` | `#f97316` |
| neutral | `white/10` | translucent white |

---

## 9. Cosmic backdrop (landing page)

The signature "deep space" background — gradient + nebulae + starfield.

### Base gradient
Source: `apps/metis-web/components/shell/starscape-backdrop.tsx`.

| Stop | Hex | Role |
|---|---|---|
| Top | `#04060d` | Near-black space |
| Middle | `#050811` | Dark navy |
| Bottom | `#04050c` | Black-blue |

### Nebula palette
Source: `apps/metis-web/lib/landing-nebulae.ts:48-56`.
Procedurally placed; each nebula uses an opacity range for depth.

| RGB | Mood |
|---|---|
| `rgb(14, 22, 60)` | Deep navy |
| `rgb(20, 15, 35)` | Dark plum |
| `rgb(10, 18, 48)` | Ink blue |
| `rgb(44, 18, 56)` | Dim violet |
| `rgb(10, 30, 52)` | Deep teal |
| `rgb(38, 14, 30)` | Wine |
| `rgb(12, 30, 24)` | Forest deep |

### Atmospheric blobs
| Colour | Role |
|---|---|
| `rgba(42,90,158,0.16)` | Ocean-blue blur (top-left) |
| `rgba(14,55,116,0.12)` | Navy blur (top-right) |
| `rgba(24,44,96,0.12)` | Slate-blue blur (bottom-left) |
| `rgba(173,198,255,0.09)` | Centre soft-blue haze |

---

## 10. Hero / FAB / home accents

The home-screen "central star" that anchors the visual identity.
Source: `apps/metis-web/components/home/`.

### Central star FAB (gold)
| Stop | Hex |
|---|---|
| Glow start | `#fff5dc` (warm cream) |
| Glow mid | `#e8c882` (gold) |
| Glow end | `#c4953a` (bronze) |
| Star core | `#fff5dc` |
| Highlight | `#ffffff` |
| Ambient stars | `#d4c3a0` (muted tan) |

### Neuron / chat icon (blue)
| Stop | Hex |
|---|---|
| Gradient start | `#3B82F6` (bright blue) |
| Gradient end | `#1E3A8A` (deep blue) |
| Stroke | `#60A5FA` |
| Light points | `#BFDBFE` |
| Connections | `#93C5FD` |

---

## 11. Recommended brand palette (for branding team)

If the branding team needs a **condensed master palette** for external assets (decks, swag, social, etc.), the following five-colour set captures the METIS identity:

| Role | Name | OKLCh | Hex |
|---|---|---|---|
| **Primary** | Cosmic Blue | `oklch(0.72 0.11 205)` | `#5fb8d9` |
| **Accent** | METIS Gold | `oklch(0.72 0.12 78)` | `#d4a443` |
| **Deep base** | Space Black | `oklch(0.09 0.018 248)` | `#0c0f17` |
| **Surface** | Ink Navy | `oklch(0.12 0.018 247)` | `#11151e` |
| **Highlight** | Star White | `oklch(0.95 0.008 235)` | `#ecedf0` |

Supporting accents drawn from the brain-graph node palette (`#6366f1` indigo, `#a371f7` purple, `#2da44e` green, `#db61a2` pink) are available when category-coding is needed.

---

## Source files

- `apps/metis-web/app/tokens.css` — core design tokens (light + dark)
- `apps/metis-web/components/shell/hud/hud-themes.ts` — HUD semantic vars
- `apps/metis-web/components/brain/brain-graph.tsx` — node / edge palette
- `apps/metis-web/components/shell/status-pill.tsx` — status colours
- `apps/metis-web/components/shell/metis-companion-dock.tsx` — activity colours
- `apps/metis-web/components/shell/starscape-backdrop.tsx` — cosmic backdrop
- `apps/metis-web/lib/landing-nebulae.ts` — nebula palette
- `apps/metis-web/components/home/` — hero / FAB accents
- `apps/metis-web-lite/src/styles/tokens.css` — minimal lite-mode palette

> **Note on hex approximations:** OKLCh→hex conversions are approximate (OKLCh covers a wider gamut than sRGB). For pixel-exact rendering, use the OKLCh value directly in modern browsers (CSS Color Module 4). Use the hex columns for print, legacy tooling, and brand-asset generation.
