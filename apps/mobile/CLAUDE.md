# apps/mobile — Replica AI Mobile

React Native app built with Expo SDK 52 + Expo Router v4. Talks exclusively to `apps/api` (FastAPI, port 8000).

## Stack

- **Framework:** Expo SDK 52, React Native 0.76
- **Navigation:** Expo Router v4 (file-based, same mental model as Next.js App Router)
- **Styling:** NativeWind v4 (Tailwind CSS for React Native)
- **Server state:** TanStack Query v5
- **HTTP:** axios with JWT interceptor (auto-refresh on 401)
- **Auth storage:** expo-secure-store (never AsyncStorage for tokens)

## Project structure

```
apps/mobile/
├── app/                    # Expo Router — file = route
│   ├── _layout.tsx         # Root: providers (QueryClient, AuthProvider)
│   ├── index.tsx           # Entry: redirects to (auth) or (tabs)
│   ├── +not-found.tsx
│   ├── (auth)/             # Unauthenticated stack
│   │   ├── login.tsx
│   │   └── register.tsx
│   └── (tabs)/             # Authenticated tab bar
│       ├── index.tsx       # Chat
│       ├── knowledge.tsx   # Knowledge base
│       └── settings.tsx    # Settings / sign out
├── src/
│   ├── api/
│   │   ├── client.ts       # axios instance + JWT interceptors
│   │   └── endpoints.ts    # All API path constants
│   ├── context/
│   │   └── AuthContext.tsx # Auth state + signIn/signOut
│   └── store/
│       └── auth.ts         # expo-secure-store token helpers
├── global.css              # Tailwind entry point (imported in root _layout)
└── tailwind.config.js
```

## Key conventions

- **Imports:** Use `@/` for `src/` (e.g. `@/api/client`, `@/context/AuthContext`).
- **Styling:** Use NativeWind `className` props. No StyleSheet.create unless needed for animations.
- **Colors:** Dark theme. Background `bg-black`, cards `bg-zinc-900`, borders `border-zinc-800`, accent `bg-brand` / `text-brand` (`#6366f1`).
- **Safe area:** Wrap tab screens with `<SafeAreaView className="flex-1 bg-black">` from `react-native-safe-area-context`.
- **API calls:** Always via `apiClient` from `@/api/client` — never use `fetch` directly.
- **Auth guard:** The `app/index.tsx` redirect handles auth routing. Never add navigation logic to individual screens.
- **Token refresh:** Handled automatically in `src/api/client.ts`. Do not add refresh logic elsewhere.

## Env vars

All runtime config via `EXPO_PUBLIC_` prefix (required for client-side access in Expo):

| Variable | Description |
|---|---|
| `EXPO_PUBLIC_API_URL` | FastAPI base URL (e.g. `http://192.168.1.x:8000` for local dev) |
| `EXPO_PUBLIC_WS_URL` | WebSocket base URL (same host, `ws://` scheme) |

Copy `.env.example` to `.env.local`. For physical device testing, use your machine's LAN IP, not `localhost`.

## WebSocket endpoints (for Part 3+)

Defined in `src/api/endpoints.ts` as `WS_ENDPOINTS`. Connect with:
```ts
const url = `${process.env.EXPO_PUBLIC_WS_URL}${WS_ENDPOINTS.CHAT(ownerId, accessToken)}`;
```

Close codes: `4001` = invalid token, `4004` = expired token (refresh and reconnect).

## Dev

```bash
cd apps/mobile
npm install
npx expo start          # opens Expo Dev Tools — scan QR with Expo Go
```

Or from repo root:
```bash
npm run dev --workspace=@replica-ai/mobile
```

## Adding new tabs

Add a file to `app/(tabs)/` — Expo Router picks it up automatically. Register it in `app/(tabs)/_layout.tsx` with a `<Tabs.Screen>` entry.

## Adding new stack screens

For screens that push on top of tabs (e.g. a conversation detail), add them to `app/(tabs)/` as nested routes or to `app/` root as modal screens.
