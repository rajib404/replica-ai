# Next.js Web App

## Quick Start

```bash
npm install  # from monorepo root
npx turbo dev --filter=@replica-ai/web
```

Runs on http://localhost:3000.

## Adding shadcn/ui Components

```bash
cd apps/web
npx shadcn-ui@latest add button
```

Components are installed to `src/components/ui/`.

## Creating Pages

1. Add a directory in `src/app/<route>/`.
2. Create `page.tsx` (server component by default).
3. Only add `"use client"` if the page needs interactivity.
4. Fetch data from the FastAPI backend — never query the database directly.
