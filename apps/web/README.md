# apps/web — Trading Platform frontend

Next.js (App Router) · React 19 · TypeScript strict · Tailwind v4 · shadcn/ui · TanStack Query · Zustand · Lightweight Charts.

## Commands

```bash
pnpm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WS_URL
pnpm dev                           # http://localhost:3000
pnpm build && pnpm start
pnpm lint
pnpm gen:api                       # regenerate lib/api/generated.ts from the running API's OpenAPI
```

## Layout

- `app/(auth)/login` — password login; tokens kept in memory + localStorage, refreshed on 401.
- `app/(app)/*` — authenticated shell (`components/layout/AppShell`): grouped sidebar covering all 15 master-prompt items, top bar with session clock, provider status chip and user menu.
- `components/design/` — `DataStateBadge`, `ModeTag`, `AiBadge`, `Money`, `Pct`, `PanelCard`, `EmptyState`, `PhasePlaceholder`.
- `lib/api/` — fetch wrapper (`client.ts`), react-query hooks (`queries.ts`), generated types (`generated.ts`, never hand-edit beyond the placeholder).
- `lib/format/` — Indian money grouping, IST time, ages. `lib/ws/store.ts` — realtime state (disconnected until a real message arrives).
- `lib/nav.ts` — sidebar groups and the phase each page ships in.

## Rules (docs/architecture/06-ui-page-map.md)

No numeric value renders without a data-state badge. No fabricated prices: a tile shows `—` and **Disconnected** until the API returns a real quote. Paper and live are tagged everywhere. Purple marks LLM output.
