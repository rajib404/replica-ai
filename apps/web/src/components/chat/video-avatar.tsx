'use client';

import { cn } from '@/lib/utils';

interface VideoAvatarProps {
  isSpeaking: boolean;
  color?: string;
  initials?: string;
  size?: 'sm' | 'md' | 'lg';
}

const sizeMap = {
  sm: { outer: 'h-20 w-20', inner: 'h-16 w-16', text: 'text-lg' },
  md: { outer: 'h-32 w-32', inner: 'h-28 w-28', text: 'text-3xl' },
  lg: { outer: 'h-48 w-48', inner: 'h-40 w-40', text: 'text-5xl' },
};

export function VideoAvatar({
  isSpeaking,
  color = 'indigo',
  initials = 'AI',
  size = 'lg',
}: VideoAvatarProps) {
  const s = sizeMap[size];

  return (
    <div className="relative flex items-center justify-center">
      {/* Outer pulsing ring */}
      <div
        className={cn(
          'absolute rounded-full transition-transform duration-300',
          s.outer,
          isSpeaking
            ? 'animate-[pulse-ring_1.5s_ease-in-out_infinite] bg-indigo-500/20'
            : 'bg-indigo-500/10',
        )}
      />

      {/* Second ring for depth */}
      {isSpeaking && (
        <div
          className={cn(
            'absolute rounded-full bg-indigo-500/10',
            s.outer,
            'animate-[pulse-ring_1.5s_ease-in-out_infinite_0.3s]',
          )}
        />
      )}

      {/* Inner circle with initials */}
      <div
        className={cn(
          'relative flex items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 shadow-lg',
          s.inner,
        )}
      >
        {isSpeaking ? (
          <AudioWaveform />
        ) : (
          <span className={cn('font-bold text-white', s.text)}>{initials}</span>
        )}
      </div>
    </div>
  );
}

function AudioWaveform() {
  return (
    <div className="flex h-10 items-end gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="w-1 rounded-full bg-white/90 animate-[waveform_0.8s_ease-in-out_infinite]"
          style={{
            animationDelay: `${i * 0.1}s`,
            height: '8px',
          }}
        />
      ))}
    </div>
  );
}
