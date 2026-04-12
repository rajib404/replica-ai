---
paths:
  - "apps/web/**"
---

## Next.js Frontend Rules

- Server components by default. Only add `"use client"` when strictly necessary.
- Use absolute imports with `@/` prefix. Example: `import { cn } from '@/lib/utils'`.
- All data fetching happens in server components or Next.js route handlers — never `useEffect` for fetching.
- UI primitives go in `src/components/ui/` (shadcn/ui). Feature components go in `src/components/`.
- Use `cn()` for combining Tailwind classes conditionally.
- API calls go to the FastAPI backend via `NEXT_PUBLIC_API_URL` — the web app never talks to the database directly.
- Shared types come from `@replica-ai/shared` — do not redefine them.
