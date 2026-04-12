'use client';

import { useCallback, useRef, useState } from 'react';
import { useSwipeable } from 'react-swipeable';
import { Copy, Reply, Trash2 } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { MessageBubble, type ChatMessage } from '@/components/chat/message-bubble';
import { Button } from '@/components/ui/button';
import { useHaptic } from '@/lib/hooks/use-haptic';
import { cn } from '@/lib/utils';

interface SwipeableMessageProps {
  message: ChatMessage;
  onDelete?: () => void;
  onCopy?: () => void;
  onReply?: () => void;
}

const LONG_PRESS_MS = 500;
const REVEAL_DISTANCE = 96;

export function SwipeableMessage({
  message,
  onDelete,
  onCopy,
  onReply,
}: SwipeableMessageProps) {
  const haptic = useHaptic();
  const [revealed, setRevealed] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isPointerDown = useRef(false);

  const swipeHandlers = useSwipeable({
    onSwipedRight: () => {
      setRevealed(true);
      haptic.light();
    },
    onSwipedLeft: () => {
      setRevealed(false);
    },
    delta: 40,
    trackTouch: true,
    trackMouse: false,
  });

  const cancelLongPress = useCallback(() => {
    isPointerDown.current = false;
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }, []);

  const handlePointerDown = useCallback(() => {
    isPointerDown.current = true;
    longPressTimer.current = setTimeout(() => {
      if (!isPointerDown.current) return;
      haptic.medium();
      setSheetOpen(true);
    }, LONG_PRESS_MS);
  }, [haptic]);

  const handleAction = useCallback(
    (action: () => void) => {
      action();
      setSheetOpen(false);
      setRevealed(false);
    },
    [],
  );

  if (message.role === 'system') {
    return <MessageBubble message={message} />;
  }

  return (
    <>
      <div
        {...swipeHandlers}
        onPointerDown={handlePointerDown}
        onPointerUp={cancelLongPress}
        onPointerCancel={cancelLongPress}
        onPointerLeave={cancelLongPress}
        className="relative overflow-hidden"
      >
        <div
          className={cn(
            'transition-transform duration-200 ease-out',
            revealed && 'translate-x-24',
          )}
        >
          <MessageBubble message={message} />
        </div>
        {revealed && (
          <div className="absolute inset-y-0 left-0 flex items-center gap-1 pl-2">
            {onCopy && (
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                onClick={() => handleAction(onCopy)}
                aria-label="Copy"
              >
                <Copy className="h-4 w-4" />
              </Button>
            )}
            {onReply && (
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                onClick={() => handleAction(onReply)}
                aria-label="Reply"
              >
                <Reply className="h-4 w-4" />
              </Button>
            )}
            {onDelete && (
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-destructive"
                onClick={() => handleAction(onDelete)}
                aria-label="Delete"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        )}
      </div>

      <Dialog.Root open={sheetOpen} onOpenChange={setSheetOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=open]:fade-in" />
          <Dialog.Content
            className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl bg-card p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom"
            aria-describedby={undefined}
          >
            <Dialog.Title className="sr-only">Message actions</Dialog.Title>
            <div className="mx-auto mb-3 h-1 w-12 rounded-full bg-muted" />
            <div className="flex flex-col gap-1">
              {onCopy && (
                <Button
                  variant="ghost"
                  className="h-12 justify-start gap-3"
                  onClick={() => handleAction(onCopy)}
                >
                  <Copy className="h-5 w-5" />
                  Copy
                </Button>
              )}
              {onReply && (
                <Button
                  variant="ghost"
                  className="h-12 justify-start gap-3"
                  onClick={() => handleAction(onReply)}
                >
                  <Reply className="h-5 w-5" />
                  Reply
                </Button>
              )}
              {onDelete && (
                <Button
                  variant="ghost"
                  className="h-12 justify-start gap-3 text-destructive"
                  onClick={() => handleAction(onDelete)}
                >
                  <Trash2 className="h-5 w-5" />
                  Delete
                </Button>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
