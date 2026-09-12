'use client';

import { useState, useRef, useEffect, useCallback, type KeyboardEvent, type ChangeEvent } from 'react';
import { Mic, MicOff, Mic2, Square, Film, Paperclip, Send, X, FileText, Camera } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { useIsTouchDevice } from '@/lib/hooks/use-media-query';
import { useHaptic } from '@/lib/hooks/use-haptic';

interface ChatInputProps {
  onSend: (text: string) => void;
  onFileAttach?: (file: File) => void;
  onVoiceClip?: (blob: Blob) => void;
  onVoiceMessage?: (file: File) => void;
  onVideoRecord?: () => void;
  disabled?: boolean;
  initialText?: string;
}

const ALLOWED_FILE_TYPES = [
  '.pdf', '.docx', '.txt', '.csv',
  '.wav', '.mp3', '.m4a', '.ogg', '.flac',
  '.mp4', '.mov', '.avi', '.mkv', '.webm',
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif',
];

// Auto-stop a voice message recording after this much continuous silence.
const VOICE_MESSAGE_SILENCE_TIMEOUT_MS = 2 * 60 * 1000;
const VOICE_MESSAGE_SILENCE_THRESHOLD = 0.02;

export function ChatInput({ onSend, onFileAttach, onVoiceClip, onVoiceMessage, onVideoRecord, disabled, initialText }: ChatInputProps) {
  const [text, setText] = useState(initialText ?? '');
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isRecordingMessage, setIsRecordingMessage] = useState(false);
  const [messageDuration, setMessageDuration] = useState(0);
  const [messageAudioLevel, setMessageAudioLevel] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<unknown>(null);
  const messageStreamRef = useRef<MediaStream | null>(null);
  const messageRecorderRef = useRef<MediaRecorder | null>(null);
  const messageChunksRef = useRef<Blob[]>([]);
  const messageAudioCtxRef = useRef<AudioContext | null>(null);
  const messageAnimationRef = useRef<number>(0);
  const messageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messageSilenceStartRef = useRef<number | null>(null);
  const isTouchDevice = useIsTouchDevice();
  const haptic = useHaptic();

  useEffect(() => {
    if (initialText && initialText !== text) {
      setText(initialText);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) {
          el.style.height = 'auto';
          el.style.height = Math.min(el.scrollHeight, 160) + 'px';
          el.focus();
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialText]);

  // Stop recording on unmount
  useEffect(() => {
    return () => {
      stopRecording(false);
      stopVoiceMessageRecording();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopRecording = useCallback((emitClip = true) => {
    (recognitionRef.current as { stop?: () => void } | null)?.stop?.();
    recognitionRef.current = null;

    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      mediaRecorderRef.current = null;
      setIsRecording(false);
      return;
    }

    recorder.onstop = () => {
      if (emitClip && audioChunksRef.current.length > 0) {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
        onVoiceClip?.(blob);
      }
      audioChunksRef.current = [];
      mediaRecorderRef.current = null;
    };

    recorder.stop();
    recorder.stream.getTracks().forEach((t) => t.stop());
    setIsRecording(false);
  }, [onVoiceClip]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // MediaRecorder for the audio blob
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.start(250);
      mediaRecorderRef.current = recorder;

      // SpeechRecognition for live transcription
      /* eslint-disable */
      const SpeechRecognitionImpl =
        (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
      if (SpeechRecognitionImpl) {
        const recognition: any = new SpeechRecognitionImpl();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        let finalTranscript = '';
        recognition.onresult = (e: any) => {
          let interim = '';
          for (let i = e.resultIndex; i < e.results.length; i++) {
            const res = e.results[i];
            if (res.isFinal) {
              finalTranscript += res[0].transcript;
            } else {
              interim += res[0].transcript;
            }
          }
          setText(finalTranscript + interim);
          resizeTextarea();
        };
        recognition.start();
        recognitionRef.current = recognition;
      }
      /* eslint-enable */

      setIsRecording(true);
      haptic.light();
    } catch {
      // Microphone denied — silently ignore
    }
  }, [haptic]);

  const stopVoiceMessageRecording = useCallback(() => {
    if (messageAnimationRef.current) {
      cancelAnimationFrame(messageAnimationRef.current);
      messageAnimationRef.current = 0;
    }
    if (messageTimerRef.current) {
      clearInterval(messageTimerRef.current);
      messageTimerRef.current = null;
    }
    messageSilenceStartRef.current = null;

    const recorder = messageRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      setIsRecordingMessage(false);
      setMessageDuration(0);
      setMessageAudioLevel(0);
    }
  }, []);

  const startVoiceMessageRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      messageStreamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      messageRecorderRef.current = recorder;
      messageChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) messageChunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(messageChunksRef.current, { type: recorder.mimeType });
        messageChunksRef.current = [];

        stream.getTracks().forEach((t) => t.stop());
        messageStreamRef.current = null;
        messageRecorderRef.current = null;

        if (messageAudioCtxRef.current) {
          messageAudioCtxRef.current.close().catch(() => {});
          messageAudioCtxRef.current = null;
        }

        setIsRecordingMessage(false);
        setMessageDuration(0);
        setMessageAudioLevel(0);

        if (blob.size > 0) {
          const file = new File([blob], `voice-message-${Date.now()}.webm`, { type: blob.type });
          onVoiceMessage?.(file);
        }
      };

      // Volume monitoring drives the progress animation and detects silence
      // so the recording can auto-stop after a period of no input.
      const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioCtx();
      messageAudioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);

      const data = new Uint8Array(analyser.frequencyBinCount);
      messageSilenceStartRef.current = null;
      const monitor = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length / 255;
        setMessageAudioLevel(avg);

        if (avg < VOICE_MESSAGE_SILENCE_THRESHOLD) {
          if (messageSilenceStartRef.current === null) {
            messageSilenceStartRef.current = Date.now();
          } else if (Date.now() - messageSilenceStartRef.current >= VOICE_MESSAGE_SILENCE_TIMEOUT_MS) {
            stopVoiceMessageRecording();
            return;
          }
        } else {
          messageSilenceStartRef.current = null;
        }

        messageAnimationRef.current = requestAnimationFrame(monitor);
      };
      monitor();

      recorder.start(250);
      setIsRecordingMessage(true);
      setMessageDuration(0);
      haptic.light();

      messageTimerRef.current = setInterval(() => {
        setMessageDuration((d) => d + 1);
      }, 1000);
    } catch {
      // Microphone denied — silently ignore
    }
  }, [haptic, onVoiceMessage, stopVoiceMessageRecording]);

  function formatMessageDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  function resizeTextarea() {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed && !attachedFile) return;

    haptic.light();

    // Stop recording and emit clip before sending
    if (isRecording) {
      stopRecording(true);
    }

    if (attachedFile) {
      onFileAttach?.(attachedFile);
      setAttachedFile(null);
    }
    if (trimmed) {
      onSend(trimmed);
    }
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInput() {
    resizeTextarea();
  }

  function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setAttachedFile(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function handleCameraCapture(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      onFileAttach?.(file);
      haptic.medium();
    }
    if (cameraInputRef.current) {
      cameraInputRef.current.value = '';
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  }

  const canSend = (!!text.trim() || !!attachedFile || isRecording) && !disabled;

  return (
    <div className="border-t bg-card p-4">
      {/* Attached file preview */}
      {attachedFile && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="flex-1 truncate text-sm">{attachedFile.name}</span>
          <Badge variant="outline" className="shrink-0 text-[10px]">
            {formatFileSize(attachedFile.size)}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5 shrink-0"
            onClick={() => setAttachedFile(null)}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      <div className="mx-auto flex max-w-3xl items-end gap-2">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={ALLOWED_FILE_TYPES.join(',')}
          onChange={handleFileSelect}
        />

        {/* Hidden camera / photo picker input */}
        <input
          ref={cameraInputRef}
          type="file"
          className="hidden"
          accept="image/*"
          capture={isTouchDevice ? 'environment' : undefined}
          onChange={handleCameraCapture}
        />

        {/* Attachment buttons */}
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || isRecordingMessage}
              >
                <Paperclip className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Attach file</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={() => cameraInputRef.current?.click()}
                disabled={disabled || isRecordingMessage}
                aria-label="Take photo"
              >
                <Camera className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isTouchDevice ? 'Take photo' : 'Upload image'}</TooltipContent>
          </Tooltip>

          {/* Recording-in-progress indicator */}
          {isRecordingMessage && (
            <div className="flex items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-1.5">
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-red-500" />
              <span className="font-mono text-[11px] tabular-nums text-red-500">
                {formatMessageDuration(messageDuration)}
              </span>
              <VoiceMessageBars level={messageAudioLevel} />
            </div>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={isRecordingMessage ? 'destructive' : 'ghost'}
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={isRecordingMessage ? stopVoiceMessageRecording : startVoiceMessageRecording}
                disabled={disabled || isRecording}
              >
                {isRecordingMessage ? <Square className="h-4 w-4" /> : <Mic2 className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isRecordingMessage ? 'Stop recording' : 'Record a Voice Message'}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={onVideoRecord}
                disabled={disabled || isRecordingMessage}
              >
                <Film className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Record video message</TooltipContent>
          </Tooltip>
        </div>

        {/* Text input */}
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder={isRecording ? 'Speak now…' : 'Type a message…'}
            rows={1}
            disabled={disabled}
            className="w-full resize-none rounded-lg border bg-background px-4 py-2.5 pr-12 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant={isRecording ? 'destructive' : 'ghost'}
                size="icon"
                className="absolute bottom-1.5 right-1.5 h-7 w-7 shrink-0"
                onClick={isRecording ? () => stopRecording(true) : startRecording}
                disabled={disabled || isRecordingMessage}
              >
                {isRecording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isRecording ? 'Stop recording' : 'Voice chat'}</TooltipContent>
          </Tooltip>
        </div>

        {/* Send button */}
        <Button
          size="icon"
          className="h-9 w-9 shrink-0"
          onClick={handleSend}
          disabled={!canSend}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function VoiceMessageBars({ level }: { level: number }) {
  const bars = [0.5, 1, 0.75, 1.15, 0.6];
  return (
    <div className="flex h-3 items-center gap-0.5">
      {bars.map((factor, i) => (
        <div
          key={i}
          className="w-0.5 shrink-0 rounded-full bg-red-500 transition-all duration-100"
          style={{ height: `${Math.max(2, level * factor * 12)}px` }}
        />
      ))}
    </div>
  );
}
