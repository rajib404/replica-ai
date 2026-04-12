'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Mic, MicOff, PhoneOff, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { VideoAvatar } from '@/components/chat/video-avatar';
import { useVideoSocket } from '@/lib/use-video-socket';
import type { VoiceStatus } from '@/lib/use-voice-socket';
import type { ChatSource } from '@/lib/use-chat-socket';
import { cn } from '@/lib/utils';

interface VideoCallViewProps {
  ownerId: string;
  onEnd: () => void;
  onMessage?: (msg: {
    text: string;
    messageId: string;
    threadId: string;
    sources: ChatSource[];
    isLearning: boolean;
    role: 'user' | 'assistant';
  }) => void;
}

export function VideoCallView({ ownerId, onEnd, onMessage }: VideoCallViewProps) {
  const [muted, setMuted] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle');
  const [faceVerified, setFaceVerified] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [callDuration, setCallDuration] = useState(0);
  const [responseText, setResponseText] = useState('');

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const faceIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleTranscript = useCallback((t: { text: string; isFinal: boolean }) => {
    setTranscript(t.text);
    if (t.isFinal && t.text) {
      onMessage?.({
        text: t.text,
        messageId: `voice-user-${Date.now()}`,
        threadId: '',
        sources: [],
        isLearning: false,
        role: 'user',
      });
    }
  }, [onMessage]);

  const handleResponseText = useCallback(
    (resp: {
      text: string;
      messageId: string;
      threadId: string;
      sources: Array<{ entry_id: string; content_type: string; score: number }>;
      isLearning: boolean;
    }) => {
      setResponseText(resp.text);
      onMessage?.({
        text: resp.text,
        messageId: resp.messageId,
        threadId: resp.threadId,
        sources: resp.sources,
        isLearning: resp.isLearning,
        role: 'assistant',
      });
    },
    [onMessage],
  );

  const handleAudioOut = useCallback(
    (_meta: { format: string; durationMs: number }, audioBlob: Blob) => {
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.play().catch(() => {});
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setVoiceStatus('idle');
      };
    },
    [],
  );

  const handleDone = useCallback((_messageId: string, _threadId: string) => {
    setTranscript('');
    // responseText stays visible briefly
    setTimeout(() => setResponseText(''), 5000);
  }, []);

  const handleStatusChange = useCallback((s: VoiceStatus) => {
    setVoiceStatus(s);
  }, []);

  const handleFaceResult = useCallback((result: { verified: boolean }) => {
    setFaceVerified(result.verified);
  }, []);

  const handleError = useCallback((detail: string) => {
    setVoiceStatus('idle');
    console.error('Video call error:', detail);
  }, []);

  const {
    connectionStatus,
    sendAudioChunk,
    startAudio,
    endAudio,
    sendFaceFrame,
    disconnect,
  } = useVideoSocket({
    ownerId,
    enabled: true,
    onTranscript: handleTranscript,
    onResponseText: handleResponseText,
    onAudioOut: handleAudioOut,
    onDone: handleDone,
    onStatusChange: handleStatusChange,
    onFaceResult: handleFaceResult,
    onError: handleError,
  });

  // Start camera + audio on mount
  useEffect(() => {
    let cancelled = false;

    async function setup() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: 320 }, height: { ideal: 240 } },
          audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        mediaStreamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch {
        console.error('Camera/mic access denied');
      }
    }
    setup();

    // Call duration timer
    durationIntervalRef.current = setInterval(() => {
      setCallDuration((d) => d + 1);
    }, 1000);

    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);

  // Start continuous audio recording when connected + not muted
  useEffect(() => {
    if (connectionStatus !== 'connected' || muted || !mediaStreamRef.current) return;

    const audioStream = new MediaStream(mediaStreamRef.current.getAudioTracks());
    const recorder = new MediaRecorder(audioStream, {
      mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm',
    });
    mediaRecorderRef.current = recorder;

    startAudio('webm');

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        e.data.arrayBuffer().then((buf) => sendAudioChunk(buf));
      }
    };

    recorder.start(250);

    return () => {
      if (recorder.state !== 'inactive') {
        recorder.stop();
      }
      endAudio();
    };
  }, [connectionStatus, muted, startAudio, sendAudioChunk, endAudio]);

  // Face frame capture interval
  useEffect(() => {
    if (connectionStatus !== 'connected') return;

    faceIntervalRef.current = setInterval(() => {
      captureAndSendFace();
    }, 5000);

    // Send first frame immediately
    captureAndSendFace();

    return () => {
      if (faceIntervalRef.current) {
        clearInterval(faceIntervalRef.current);
        faceIntervalRef.current = null;
      }
    };
  }, [connectionStatus, sendFaceFrame]);

  function captureAndSendFace() {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (video.videoWidth === 0) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) {
          blob.arrayBuffer().then((buf) => sendFaceFrame(buf));
        }
      },
      'image/jpeg',
      0.8,
    );
  }

  function cleanup() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (faceIntervalRef.current) {
      clearInterval(faceIntervalRef.current);
    }
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
    }
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
    }
    disconnect();
  }

  function handleEnd() {
    cleanup();
    onEnd();
  }

  function toggleMute() {
    setMuted((m) => {
      const newMuted = !m;
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getAudioTracks().forEach((t) => {
          t.enabled = !newMuted;
        });
      }
      return newMuted;
    });
  }

  function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  const isSpeaking = voiceStatus === 'speaking';

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black text-white">
      {/* Hidden canvas for face capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <Clock className="h-4 w-4 text-white/60" />
          <span className="font-mono text-sm text-white/80">{formatDuration(callDuration)}</span>
        </div>
        <div className="flex items-center gap-2">
          {faceVerified ? (
            <div className="flex items-center gap-1.5 rounded-full bg-green-500/20 px-3 py-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />
              <span className="text-xs text-green-400">Face verified</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 rounded-full bg-red-500/20 px-3 py-1">
              <XCircle className="h-3.5 w-3.5 text-red-400" />
              <span className="text-xs text-red-400">Face not verified</span>
            </div>
          )}
        </div>
      </div>

      {/* Center: AI Avatar */}
      <div className="flex flex-1 items-center justify-center">
        <VideoAvatar isSpeaking={isSpeaking} />
      </div>

      {/* Transcript overlay */}
      {(transcript || responseText) && (
        <div className="absolute bottom-40 left-0 right-0 px-8 text-center">
          {transcript && (
            <p className="text-sm text-white/70 italic">&ldquo;{transcript}&rdquo;</p>
          )}
          {responseText && (
            <p className="mt-2 text-sm text-white/90">{responseText}</p>
          )}
        </div>
      )}

      {/* Bottom: local camera + controls */}
      <div className="relative px-6 pb-8 pt-4">
        {/* Local camera preview (bottom left) */}
        <div className="absolute bottom-8 left-6 overflow-hidden rounded-xl border border-white/20 shadow-lg">
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="h-[90px] w-[120px] object-cover"
          />
        </div>

        {/* Controls row (centered) */}
        <div className="flex items-center justify-center gap-6">
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              'h-12 w-12 rounded-full',
              muted ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' : 'bg-white/10 text-white hover:bg-white/20',
            )}
            onClick={toggleMute}
          >
            {muted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="h-14 w-14 rounded-full bg-red-600 text-white hover:bg-red-700"
            onClick={handleEnd}
          >
            <PhoneOff className="h-6 w-6" />
          </Button>
        </div>
      </div>
    </div>
  );
}
