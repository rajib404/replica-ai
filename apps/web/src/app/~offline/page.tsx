import { Brain, WifiOff } from 'lucide-react';

export const metadata = {
  title: "You're offline — Replica AI",
};

export default function OfflinePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary">
        <Brain className="h-8 w-8 text-primary-foreground" />
      </div>

      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-2 text-muted-foreground">
          <WifiOff className="h-5 w-5" />
          <span className="text-sm font-medium uppercase tracking-wide">Offline</span>
        </div>
        <h1 className="text-2xl font-bold">You&apos;re offline</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Replica AI can&apos;t reach the network right now. Cached chats and knowledge entries
          are still available — your messages will be queued and sent automatically as soon as
          you&apos;re back online.
        </p>
      </div>

      <a
        href="/dashboard/chat"
        className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        Try again
      </a>
    </div>
  );
}
