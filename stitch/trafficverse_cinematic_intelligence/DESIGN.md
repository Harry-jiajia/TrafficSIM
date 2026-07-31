---
name: TrafficVerse Cinematic Intelligence
colors:
  surface: '#10131c'
  surface-dim: '#10131c'
  surface-bright: '#363943'
  surface-container-lowest: '#0b0e16'
  surface-container-low: '#191b24'
  surface-container: '#1d1f28'
  surface-container-high: '#272a33'
  surface-container-highest: '#32343e'
  on-surface: '#e1e2ee'
  on-surface-variant: '#c2c6d8'
  inverse-surface: '#e1e2ee'
  inverse-on-surface: '#2e303a'
  outline: '#8c90a1'
  outline-variant: '#424656'
  surface-tint: '#b3c5ff'
  primary: '#b3c5ff'
  on-primary: '#002b75'
  primary-container: '#0066ff'
  on-primary-container: '#f8f7ff'
  inverse-primary: '#0054d6'
  secondary: '#bdf4ff'
  on-secondary: '#00363d'
  secondary-container: '#00e3fd'
  on-secondary-container: '#00616d'
  tertiary: '#ffb59d'
  on-tertiary: '#5d1900'
  tertiary-container: '#cc4204'
  on-tertiary-container: '#fff6f4'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dae1ff'
  primary-fixed-dim: '#b3c5ff'
  on-primary-fixed: '#001849'
  on-primary-fixed-variant: '#003fa4'
  secondary-fixed: '#9cf0ff'
  secondary-fixed-dim: '#00daf3'
  on-secondary-fixed: '#001f24'
  on-secondary-fixed-variant: '#004f58'
  tertiary-fixed: '#ffdbd0'
  tertiary-fixed-dim: '#ffb59d'
  on-tertiary-fixed: '#390c00'
  on-tertiary-fixed-variant: '#832600'
  background: '#10131c'
  on-background: '#e1e2ee'
  surface-variant: '#32343e'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-xs:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  gutter: 16px
  sidebar-width: 260px
  card-gap: 12px
---

## Brand & Style

This design system is engineered for high-stakes simulation and real-time autonomous traffic monitoring. The aesthetic follows a **High-Tech / Glassmorphic** direction, prioritizing deep immersion and rapid data processing. 

The atmosphere is "Mission Control"—professional, authoritative, and futuristic. It uses high-contrast accents against an abyssal background to ensure that critical alerts (accidents, warnings) are immediately perceptible. The visual language balances dense information displays with semi-transparent layering to maintain a sense of physical depth and spatial hierarchy within the simulation environment.

Key principles include:
- **Precision:** Every border, pixel, and alignment must feel intentional and engineered.
- **Urgency:** Status-driven color usage that cuts through the dark UI.
- **Depth:** Using Z-axis layering (glassmorphism) to separate controls from the live map and data streams.

## Colors

The palette is anchored in **Deep Navy and Charcoal** to minimize eye strain during long monitoring sessions and to provide maximum contrast for the bright data overlays.

- **Primary (Electric Blue):** Used for primary actions, active navigation states, and the core brand presence.
- **Secondary (Cyan):** Used for specific telemetry data and "System Ready" indicators.
- **Functional Palette:** 
    - **Safe (Green):** Indicates L3 autonomy or nominal traffic flow.
    - **Warning (Orange):** Highlights congestion or sensor degradation.
    - **Critical (Red):** Reserved strictly for accidents, collisions, or system failures.
- **Borders:** Thin, low-opacity strokes (#2A2F3A) are used to define component boundaries without creating visual clutter.

## Typography

The system utilizes **Inter** for its neutral, highly legible character, particularly essential for dense dashboard layouts. 

For telemetry, timestamps, and coordinate data, **JetBrains Mono** is introduced to provide a "technical" feel and ensure that numerical values align perfectly in tables and gauges.

**Scaling Rules:**
- Use **Display-LG** for primary scene titles or major KPI numbers.
- Use **Data-Mono** for all changing variables (speed, coordinates, IDs) to prevent layout shifting as numbers fluctuate.
- Maintain a minimum of 400 weight for body text to ensure readability against the dark background.

## Layout & Spacing

This design system uses a **Fixed Grid for Dashboards** and a **Fluid Layout for the Map Viewer**.

- **Structure:** A fixed left sidebar (260px) anchors the navigation. The main stage is divided into a "Primary Viewport" (Map or 3D Render) and "Telemetric Panels" (Sidebar cards or bottom drawers).
- **Rhythm:** A 4px baseline grid ensures tight, engineering-grade alignment. 
- **Density:** High density. Gaps between cards are kept at 12px to maximize the screen real estate for visualization widgets.
- **Safe Zones:** Always maintain a 24px margin around the primary window edges to prevent UI elements from feeling cramped against the hardware bezel.

## Elevation & Depth

Visual hierarchy is established through **Backdrop Blurs** and **Tonal Layering** rather than traditional drop shadows.

- **Level 0 (Base):** Deep Navy (#0B0E14) - The bottom-most simulation layer.
- **Level 1 (Cards/Panels):** Charcoal (#141820) with a 1px border.
- **Level 2 (Overlays/Modals):** Glassmorphic surfaces using 15-20% opacity of the surface color and a 12px backdrop blur.
- **Glow Effects:** Active status indicators and critical alerts utilize a 0px 0px 8px outer glow in their respective functional color (e.g., Green for L3) to simulate a light-emitting hardware interface.

## Shapes

The shape language is **Soft (0.25rem / 4px)**. 

While rounded corners are present to provide a modern feel, they are kept minimal to maintain a "scientific" and "structured" appearance. 
- **Buttons and Inputs:** 4px radius.
- **Dashboard Cards:** 8px radius (`rounded-lg`) to clearly group complex data visualizations.
- **Status Pills:** Fully rounded (pill-shaped) to distinguish them from structural UI elements.

## Components

### Buttons & Controls
- **Primary:** Electric Blue background with a subtle inner top glow. On hover, increase brightness and add a 4px blue drop shadow.
- **Ghost:** Border-only (#2A2F3A) with subtle text. Used for secondary map tools.
- **Playback Controls:** Segmented button groups with icon-only labels for simulation speed (1x, 2x, 4x).

### Dashboard Cards
- Background: #141820 at 80% opacity with backdrop-blur.
- Header: Small uppercase labels (Label-XS) in a muted grey.
- Content: Integrated charts (Line/Bar) should use thin 1px lines and no fill, or very low-opacity area fills.

### Navigation Sidebar
- Active state: A vertical 3px blue bar on the left edge with a subtle background gradient transition from blue to transparent.
- Icons: 20px size, stroke-based (1.5px weight).

### Map Widgets
- Small, floating glassmorphic squares for zoom, tilt, and layer controls. 
- Active tools must use the Electric Blue glow.

### Input Fields
- Darker than the surface color (#090B0F).
- Focused state: Border changes to #0066FF with a faint blue outer glow.