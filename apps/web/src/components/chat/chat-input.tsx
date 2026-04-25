'use client';

import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from 'react';
import { Mic, Video, Film, Paperclip, Send, X, FileText, Camera } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { useIsTouchDevice } from '@/lib/hooks/use-media-query';
import { useHaptic } from '@/lib/hooks/use-haptic';

interface ChatInputProps {
  onSend: (text: string) => void;
  onFileAttach?: (file: File) => void;
  onVoiceToggle?: () => void;
  onVideoCall?: () => void;
  onVideoRecord?: () => void;
  voiceEnabled?: boolean;
  disabled?: boolean;
  initialText?: string;
}

const ALLOWED_FILE_TYPES = [
  '.pdf', '.docx', '.txt', '.csv',
  '.wav', '.mp3', '.m4a', '.ogg', '.flac',
  '.mp4', '.mov', '.avi', '.mkv', '.webm',
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif',
];

export function ChatInput({ onSend, onFileAttach, onVoiceToggle, onVideoCall, onVideoRecord, voiceEnabled, disabled, initialText }: ChatInputProps) {
  const [text, setText] = useState(initialText ?? '');
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const isTouchDevice = useIsTouchDevice();
  const haptic = useHaptic();

  // Apply incoming initialText (e.g. share-target redirect) without
  // clobbering in-progress typing.
  useEffect(() => {
    if (initialText && initialText !== text) {
      setText(initialText);
      // Resize textarea to fit on next paint.
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

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed && !attachedFile) return;

    haptic.light();

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
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }

  function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setAttachedFile(file);
    }
    // Reset input so same file can be re-selected
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
        <div className="flex gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
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
                disabled={disabled}
                aria-label="Take photo"
              >
                <Camera className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isTouchDevice ? 'Take photo' : 'Upload image'}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={voiceEnabled ? 'default' : 'ghost'}
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={onVoiceToggle}
                disabled={disabled}
              >
                <Mic className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{voiceEnabled ? 'Exit voice mode' : 'Voice mode'}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={onVideoCall}
                disabled={disabled}
              >
                <Video className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Video call</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={onVideoRecord}
                disabled={disabled}
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
            placeholder="Type a message..."
            rows={1}
            disabled={disabled}
            className="w-full resize-none rounded-lg border bg-background px-4 py-2.5 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
        </div>

        {/* Send button */}
        <Button
          size="icon"
          className="h-9 w-9 shrink-0"
          onClick={handleSend}
          disabled={(!text.trim() && !attachedFile) || disabled}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
