<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# 🎨 DESIGN SYSTEM RULES

When building or modifying frontend components, ALWAYS read and adhere to the guidelines in the design specialist skill file:
[design-specialist.md](file:///c:/Users/João%20Luccas/Desktop/LINKB2B/hierarchy-mapper/frontend/src/skills/design-specialist.md)

It contains strict rules, HTML/CSS structure examples, design tokens, and checklists for:
1. **Drawer** (Structural layouts, sliding-in panel animations, and active state styles)
2. **Chat Panel** (High-fidelity obsidian-style dialogue bubbles, logs, and action approval modals)
3. **Floating Toolbar** (Segmented dual-row absolute layout floating controller with glassmorphic styling)
4. **Card Node / Compact Card** (Zero-background bordered cards with seniority-based highlights)

Make sure all styling relies strictly on global CSS variables (`--sw-` and `--chat-`) to ensure perfect integration and support for light/dark themes. Do NOT hardcode colors or use raw styling outside modules.

