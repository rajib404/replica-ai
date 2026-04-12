'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Video, Square, Play, Send, X, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface VideoMessageRecorderProps {
  open: boolean;
  onClose: () => void;
  onSend: (file: File) => void;
}

type RecorderState = 'preview' | 'recording' | 'recorded';

export function VideoMessageRecorder({ open, onClose, onSend }: VideoMessageRecorderProps) {
  const [state, setState] = useState<RecorderState>('preview');
  const [duration, setDuration] = useState(0);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const playbackRef = useRef<HTMLVideoElement>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Open camera when dialog opens
  useEffect(() => {
    if (open) {
      openCamera();
    }
    return () => {
      cleanup();
    };
  }, [open]);

  async function openCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: true,
      });
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setState('preview');
    } catch {
      console.error('Camera access denied');
    }
  }

  function cleanup() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recordedUrl) {
      URL.revokeObjectURL(recordedUrl);
    }
    setState('preview');
    setDuration(0);
    setRecordedUrl(null);
    setRecordedBlob(null);
    chunksRef.current = [];
  }

  const startRecording = useCallback(() => {
    if (!mediaStreamRef.current) return;

    chunksRef.current = [];
    setDuration(0);

    const recorder = new MediaRecorder(mediaStreamRef.current, {
      mimeType: MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm',
    });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'video/webm' });
      const url = URL.createObjectURL(blob);
      setRecordedBlob(blob);
      setRecordedUrl(url);
      setState('recorded');

      // Stop camera
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
      }
    };

    recorder.start(250);
    setState('recording');

    timerRef.current = setInterval(() => {
      setDuration((d) => d + 1);
    }, 1000);
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  function handleRetake() {
    if (recordedUrl) {
      URL.revokeObjectURL(recordedUrl);
    }
    setRecordedUrl(null);
    setRecordedBlob(null);
    setDuration(0);
    openCamera();
  }

  function handleSend() {
    if (!recordedBlob) return;
    const file = new File([recordedBlob], `video-message-${Date.now()}.webm`, {
      type: 'video/webm',
    });
    onSend(file);
    handleClose();
  }

  function handleClose() {
    cleanup();
    onClose();
  }

  function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="max-w-md p-0 overflow-hidden">
        <DialogHeader className="px-4 pt-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Video className="h-4 w-4" />
            Record video message
          </DialogTitle>
        </DialogHeader>

        <div className="relative aspect-[4/3] bg-black">
          {/* Live preview */}
          {(state === 'preview' || state === 'recording') && (
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="h-full w-full object-cover"
            />
          )}

          {/* Playback preview */}
          {state === 'recorded' && recordedUrl && (
            <video
              ref={playbackRef}
              src={recordedUrl}
              controls
              playsInline
              className="h-full w-full object-cover"
            />
          )}

          {/* Recording indicator */}
          {state === 'recording' && (
            <div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1">
              <div className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
              <span className="font-mono text-xs text-white">{formatDuration(duration)}</span>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center justify-center gap-3 px-4 pb-4">
          {state === 'preview' && (
            <>
              <Button variant="ghost" size="sm" onClick={handleClose} className="gap-1">
                <X className="h-3.5 w-3.5" />
                Cancel
              </Button>
              <Button onClick={startRecording} className="gap-2">
                <Video className="h-4 w-4" />
                Record
              </Button>
            </>
          )}

          {state === 'recording' && (
            <Button variant="destructive" onClick={stopRecording} className="gap-2">
              <Square className="h-4 w-4" />
              Stop ({formatDuration(duration)})
            </Button>
          )}

          {state === 'recorded' && (
            <>
              <Button variant="outline" size="sm" onClick={handleRetake} className="gap-1">
                <RotateCcw className="h-3.5 w-3.5" />
                Retake
              </Button>
              <Button onClick={handleSend} className="gap-2">
                <Send className="h-4 w-4" />
                Send video
              </Button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
