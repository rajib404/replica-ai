'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, MicOff, Square, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { VoiceStatus } from '@/lib/use-voice-socket';
import { useHaptic } from '@/lib/hooks/use-haptic';

interface VoiceChatButtonProps {
  voiceStatus: VoiceStatus;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onCancelRecording: () => void;
  disabled?: boolean;
}

export function VoiceChatButton({
  voiceStatus,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
  disabled,
}: VoiceChatButtonProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number>(0);
  const haptic = useHaptic();

  // Audio level monitoring
  useEffect(() => {
    if (!isRecording) {
      setAudioLevel(0);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      return;
    }

    const updateLevel = () => {
      if (analyserRef.current) {
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        setAudioLevel(avg / 255);
      }
      animationRef.current = requestAnimationFrame(updateLevel);
    };
    updateLevel();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isRecording]);

  const handlePushToTalk = useCallback(() => {
    if (isRecording) {
      haptic.medium();
      setIsRecording(false);
      onStopRecording();
    } else {
      haptic.medium();
      setIsRecording(true);
      onStartRecording();
    }
  }, [isRecording, onStartRecording, onStopRecording, haptic]);

  const handleCancel = useCallback(() => {
    haptic.warning();
    setIsRecording(false);
    onCancelRecording();
  }, [onCancelRecording, haptic]);

  // Reset recording state when voice status changes to idle
  useEffect(() => {
    if (voiceStatus === 'idle' && isRecording) {
      setIsRecording(false);
    }
  }, [voiceStatus, isRecording]);

  const isProcessing = voiceStatus === 'transcribing' || voiceStatus === 'thinking';
  const isSpeaking = voiceStatus === 'speaking';

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Audio visualizer ring */}
      <div className="relative">
        {/* Pulsing ring when recording */}
        {isRecording && (
          <div
            className="absolute inset-0 rounded-full bg-red-500/20 transition-transform"
            style={{
              transform: `scale(${1 + audioLevel * 0.5})`,
            }}
          />
        )}

        {/* Speaking animation */}
        {isSpeaking && (
          <div className="absolute inset-0 animate-ping rounded-full bg-blue-500/20" />
        )}

        {/* Main button */}
        <Button
          size="icon"
          variant={isRecording ? 'destructive' : 'default'}
          className={cn(
            'relative h-14 w-14 rounded-full transition-all',
            isRecording && 'scale-110',
            isProcessing && 'animate-pulse',
            isSpeaking && 'bg-blue-600 hover:bg-blue-700',
          )}
          onClick={handlePushToTalk}
          disabled={disabled || isProcessing || isSpeaking}
        >
          {isProcessing ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : isRecording ? (
            <Square className="h-5 w-5" />
          ) : isSpeaking ? (
            <AudioWaveform />
          ) : (
            <Mic className="h-6 w-6" />
          )}
        </Button>
      </div>

      {/* Status label */}
      <span className="text-xs text-muted-foreground">
        {isRecording
          ? 'Tap to stop'
          : isProcessing
            ? voiceStatus === 'transcribing'
              ? 'Transcribing...'
              : 'Thinking...'
            : isSpeaking
              ? 'Speaking...'
              : 'Tap to talk'}
      </span>

      {/* Cancel button when recording */}
      {isRecording && (
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-muted-foreground"
          onClick={handleCancel}
        >
          <MicOff className="mr-1 h-3 w-3" />
          Cancel
        </Button>
      )}
    </div>
  );
}

function AudioWaveform() {
  return (
    <div className="flex h-6 items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="w-0.5 animate-pulse rounded-full bg-white"
          style={{
            height: `${8 + Math.random() * 16}px`,
            animationDelay: `${i * 0.1}s`,
            animationDuration: '0.6s',
          }}
        />
      ))}
    </div>
  );
}
