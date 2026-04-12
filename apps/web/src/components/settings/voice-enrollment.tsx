'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, MicOff, CheckCircle2, AlertCircle, Loader2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

const MIN_SAMPLES = 3;
const MAX_SAMPLES = 5;
const MIN_DURATION_SEC = 10;

type EnrollmentStatus = 'idle' | 'checking' | 'not_enrolled' | 'enrolled';
type RecordingState = 'idle' | 'recording' | 'uploading';

interface VoiceStatusResponse {
  enrolled: boolean;
  samples_stored: number;
  samples_required: number;
}

interface VoiceEnrollResponse {
  status: string;
  samples_received: number;
  samples_required: number;
  message: string;
}

interface VoiceCheckResponse {
  verified: boolean;
  similarity_score: number;
  threshold: number;
  message: string;
}

export function VoiceEnrollment() {
  const [enrollmentStatus, setEnrollmentStatus] = useState<EnrollmentStatus>('idle');
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [samples, setSamples] = useState<Blob[]>([]);
  const [currentDuration, setCurrentDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<VoiceCheckResponse | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  // Check enrollment status on mount
  useEffect(() => {
    checkStatus();
  }, []);

  async function checkStatus() {
    setEnrollmentStatus('checking');
    setError(null);
    try {
      const resp = await api.get<VoiceStatusResponse>('/api/verify/voice/status');
      setEnrollmentStatus(resp.enrolled ? 'enrolled' : 'not_enrolled');
    } catch {
      setEnrollmentStatus('not_enrolled');
    }
  }

  const startRecording = useCallback(async () => {
    setError(null);
    setSuccessMessage(null);
    setTestResult(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setSamples((prev) => [...prev, blob]);
        stream.getTracks().forEach((t) => t.stop());

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        setRecordingState('idle');
      };

      mediaRecorder.start(250); // collect data every 250ms
      startTimeRef.current = Date.now();
      setCurrentDuration(0);
      setRecordingState('recording');

      timerRef.current = setInterval(() => {
        setCurrentDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 500);
    } catch {
      setError('Microphone access denied. Please allow microphone permissions.');
    }
  }, []);

  const stopRecording = useCallback(() => {
    const elapsed = (Date.now() - startTimeRef.current) / 1000;
    if (elapsed < MIN_DURATION_SEC) {
      setError(`Recording too short (${Math.floor(elapsed)}s). Need at least ${MIN_DURATION_SEC}s.`);
      // Cancel instead of saving
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        const stream = mediaRecorderRef.current.stream;
        mediaRecorderRef.current.stop();
        stream.getTracks().forEach((t) => t.stop());
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setRecordingState('idle');
      // Don't save this sample
      chunksRef.current = [];
      return;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  function removeSample(index: number) {
    setSamples((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitEnrollment() {
    if (samples.length < MIN_SAMPLES) {
      setError(`Need at least ${MIN_SAMPLES} samples. You have ${samples.length}.`);
      return;
    }

    setRecordingState('uploading');
    setError(null);
    setSuccessMessage(null);

    const formData = new FormData();
    samples.forEach((blob, i) => {
      formData.append('samples', blob, `sample${i + 1}.webm`);
    });

    try {
      const token = api.getToken();
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/verify/voice/enroll`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        },
      );

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(body.detail ?? 'Enrollment failed');
      }

      const data: VoiceEnrollResponse = await resp.json();

      if (data.status === 'enrolled') {
        setSuccessMessage(data.message);
        setEnrollmentStatus('enrolled');
        setSamples([]);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Enrollment failed');
    } finally {
      setRecordingState('idle');
    }
  }

  async function testVoice() {
    setError(null);
    setTestResult(null);
    setSuccessMessage(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
      const chunks: Blob[] = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      setRecordingState('recording');
      startTimeRef.current = Date.now();
      setCurrentDuration(0);
      timerRef.current = setInterval(() => {
        setCurrentDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 500);

      mediaRecorder.start(250);

      // Record for 5 seconds then auto-stop
      await new Promise<void>((resolve) => {
        mediaRecorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          resolve();
        };
        setTimeout(() => {
          if (mediaRecorder.state !== 'inactive') mediaRecorder.stop();
        }, 5000);
      });

      setRecordingState('uploading');

      const blob = new Blob(chunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('sample', blob, 'test.webm');

      const token = api.getToken();
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/verify/voice/check`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        },
      );

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(body.detail ?? 'Verification failed');
      }

      const data: VoiceCheckResponse = await resp.json();
      setTestResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setRecordingState('idle');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Mic className="h-5 w-5" />
          Voice Verification
        </CardTitle>
        <CardDescription>
          Enroll your voice to enable biometric verification. Record {MIN_SAMPLES}-{MAX_SAMPLES} samples
          of at least {MIN_DURATION_SEC} seconds each.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status badge */}
        {enrollmentStatus === 'checking' && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Checking enrollment status...
          </div>
        )}

        {enrollmentStatus === 'enrolled' && (
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Voice enrolled
            </Badge>
          </div>
        )}

        {/* Error / Success */}
        {error && (
          <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}
        {successMessage && (
          <div className="flex items-center gap-2 rounded-md bg-green-500/10 px-3 py-2 text-sm text-green-600 dark:text-green-400">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            {successMessage}
          </div>
        )}

        {/* Enrollment flow */}
        {enrollmentStatus !== 'enrolled' && (
          <>
            {/* Samples list */}
            {samples.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  Recorded samples ({samples.length}/{MIN_SAMPLES} required)
                </p>
                {samples.map((blob, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-md border px-3 py-2"
                  >
                    <span className="text-sm">
                      Sample {i + 1} — {(blob.size / 1024).toFixed(0)} KB
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => removeSample(i)}
                      disabled={recordingState !== 'idle'}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Recording controls */}
            <div className="flex items-center gap-3">
              {recordingState === 'recording' && (
                <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                  <div className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                  Recording... {currentDuration}s
                </div>
              )}

              {recordingState === 'idle' && samples.length < MAX_SAMPLES && (
                <Button variant="outline" onClick={startRecording} className="gap-2">
                  <Mic className="h-4 w-4" />
                  Record sample {samples.length + 1}
                </Button>
              )}

              {recordingState === 'recording' && (
                <Button variant="destructive" onClick={stopRecording} className="gap-2">
                  <MicOff className="h-4 w-4" />
                  Stop recording
                </Button>
              )}

              {recordingState === 'uploading' && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enrolling voice profile...
                </div>
              )}
            </div>

            {/* Submit button */}
            {samples.length >= MIN_SAMPLES && recordingState === 'idle' && (
              <Button onClick={submitEnrollment} className="w-full">
                Enroll voice profile ({samples.length} samples)
              </Button>
            )}
          </>
        )}

        {/* Test verification (only when enrolled) */}
        {enrollmentStatus === 'enrolled' && (
          <div className="space-y-3 border-t pt-4">
            <p className="text-sm font-medium">Test verification</p>
            <p className="text-xs text-muted-foreground">
              Record a 5-second sample to test voice recognition accuracy.
            </p>

            {recordingState === 'idle' && (
              <Button variant="outline" onClick={testVoice} className="gap-2">
                <Mic className="h-4 w-4" />
                Test my voice
              </Button>
            )}

            {recordingState === 'recording' && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                Listening... {currentDuration}s / 5s
              </div>
            )}

            {recordingState === 'uploading' && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Verifying...
              </div>
            )}

            {testResult && (
              <div
                className={`rounded-md px-3 py-2 text-sm ${
                  testResult.verified
                    ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                    : 'bg-destructive/10 text-destructive'
                }`}
              >
                <p className="font-medium">{testResult.message}</p>
                <p className="mt-1 text-xs opacity-75">
                  Similarity: {(testResult.similarity_score * 100).toFixed(1)}% (threshold:{' '}
                  {(testResult.threshold * 100).toFixed(0)}%)
                </p>
              </div>
            )}

            {/* Re-enroll option */}
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground"
              onClick={() => {
                setEnrollmentStatus('not_enrolled');
                setSamples([]);
                setTestResult(null);
                setSuccessMessage(null);
              }}
            >
              Re-enroll voice profile
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
