'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Camera, CheckCircle2, AlertCircle, Loader2, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

const MIN_SAMPLES = 5;
const MAX_SAMPLES = 10;

type EnrollmentStatus = 'idle' | 'checking' | 'not_enrolled' | 'enrolled';
type CaptureState = 'idle' | 'previewing' | 'uploading';

interface FaceStatusResponse {
  enrolled: boolean;
  samples_stored: number;
  samples_required: number;
}

interface FaceEnrollResponse {
  status: string;
  samples_received: number;
  samples_required: number;
  message: string;
}

interface FaceCheckResponse {
  verified: boolean;
  confidence: number;
  threshold: number;
  message: string;
}

export function FaceEnrollment() {
  const [enrollmentStatus, setEnrollmentStatus] = useState<EnrollmentStatus>('idle');
  const [captureState, setCaptureState] = useState<CaptureState>('idle');
  const [samples, setSamples] = useState<Blob[]>([]);
  const [thumbnails, setThumbnails] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<FaceCheckResponse | null>(null);
  const [cameraActive, setCameraActive] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    checkStatus();
  }, []);

  // Cleanup camera on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  async function checkStatus() {
    setEnrollmentStatus('checking');
    setError(null);
    try {
      const resp = await api.get<FaceStatusResponse>('/api/verify/face/status');
      setEnrollmentStatus(resp.enrolled ? 'enrolled' : 'not_enrolled');
    } catch {
      setEnrollmentStatus('not_enrolled');
    }
  }

  const startCamera = useCallback(async () => {
    setError(null);
    setSuccessMessage(null);
    setTestResult(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);
      setCaptureState('previewing');
    } catch {
      setError('Camera access denied. Please allow camera permissions.');
    }
  }, []);

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
    setCaptureState('idle');
  }

  const capturePhoto = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) {
          setSamples((prev) => [...prev, blob]);
          const url = URL.createObjectURL(blob);
          setThumbnails((prev) => [...prev, url]);
        }
      },
      'image/jpeg',
      0.9,
    );
  }, []);

  function removeSample(index: number) {
    URL.revokeObjectURL(thumbnails[index]);
    setSamples((prev) => prev.filter((_, i) => i !== index));
    setThumbnails((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitEnrollment() {
    if (samples.length < MIN_SAMPLES) {
      setError(`Need at least ${MIN_SAMPLES} samples. You have ${samples.length}.`);
      return;
    }

    setCaptureState('uploading');
    setError(null);
    setSuccessMessage(null);
    stopCamera();

    const formData = new FormData();
    samples.forEach((blob, i) => {
      formData.append('samples', blob, `photo${i + 1}.jpg`);
    });

    try {
      const token = api.getToken();
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/verify/face/enroll`,
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

      const data: FaceEnrollResponse = await resp.json();

      if (data.status === 'enrolled') {
        setSuccessMessage(data.message);
        setEnrollmentStatus('enrolled');
        cleanupThumbnails();
        setSamples([]);
        setThumbnails([]);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Enrollment failed');
    } finally {
      setCaptureState('idle');
    }
  }

  function cleanupThumbnails() {
    thumbnails.forEach((url) => URL.revokeObjectURL(url));
  }

  async function testFace() {
    setError(null);
    setTestResult(null);
    setSuccessMessage(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      });

      // Show preview briefly
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);

      // Wait for video to be ready, then capture
      await new Promise<void>((resolve) => setTimeout(resolve, 1500));

      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) {
        stream.getTracks().forEach((t) => t.stop());
        setCameraActive(false);
        return;
      }

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        stream.getTracks().forEach((t) => t.stop());
        setCameraActive(false);
        return;
      }

      ctx.drawImage(video, 0, 0);

      stream.getTracks().forEach((t) => t.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      setCameraActive(false);

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob((b) => resolve(b), 'image/jpeg', 0.9),
      );

      if (!blob) {
        setError('Failed to capture photo');
        return;
      }

      setCaptureState('uploading');

      const formData = new FormData();
      formData.append('sample', blob, 'test.jpg');

      const token = api.getToken();
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/verify/face/check`,
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

      const data: FaceCheckResponse = await resp.json();
      setTestResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setCaptureState('idle');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Camera className="h-5 w-5" />
          Face Verification
        </CardTitle>
        <CardDescription>
          Enroll your face for biometric verification. Capture {MIN_SAMPLES} photos from
          different angles.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Hidden canvas for capturing */}
        <canvas ref={canvasRef} className="hidden" />

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
              Face enrolled
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
            {/* Camera preview */}
            {cameraActive && (
              <div className="relative overflow-hidden rounded-lg border">
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full max-w-sm"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-2 top-2 h-7 w-7 bg-black/40 text-white hover:bg-black/60"
                  onClick={stopCamera}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            {/* Thumbnail previews */}
            {samples.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  Captured photos ({samples.length}/{MIN_SAMPLES} required)
                </p>
                <div className="flex flex-wrap gap-2">
                  {thumbnails.map((url, i) => (
                    <div key={i} className="group relative">
                      <img
                        src={url}
                        alt={`Sample ${i + 1}`}
                        className="h-16 w-16 rounded-md border object-cover"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-destructive text-white opacity-0 group-hover:opacity-100"
                        onClick={() => removeSample(i)}
                        disabled={captureState !== 'idle' && captureState !== 'previewing'}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Capture controls */}
            <div className="flex items-center gap-3">
              {!cameraActive && captureState === 'idle' && (
                <Button variant="outline" onClick={startCamera} className="gap-2">
                  <Camera className="h-4 w-4" />
                  Open camera
                </Button>
              )}

              {cameraActive && samples.length < MAX_SAMPLES && (
                <Button variant="outline" onClick={capturePhoto} className="gap-2">
                  <Camera className="h-4 w-4" />
                  Capture photo {samples.length + 1}
                </Button>
              )}

              {captureState === 'uploading' && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enrolling face profile...
                </div>
              )}
            </div>

            {/* Submit button */}
            {samples.length >= MIN_SAMPLES && captureState !== 'uploading' && (
              <Button onClick={submitEnrollment} className="w-full">
                Enroll face profile ({samples.length} photos)
              </Button>
            )}
          </>
        )}

        {/* Test verification (only when enrolled) */}
        {enrollmentStatus === 'enrolled' && (
          <div className="space-y-3 border-t pt-4">
            <p className="text-sm font-medium">Test verification</p>
            <p className="text-xs text-muted-foreground">
              Take a photo to test face recognition accuracy.
            </p>

            {/* Camera preview for test */}
            {cameraActive && (
              <div className="relative overflow-hidden rounded-lg border">
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full max-w-sm"
                />
              </div>
            )}

            {captureState === 'idle' && !cameraActive && (
              <Button variant="outline" onClick={testFace} className="gap-2">
                <Camera className="h-4 w-4" />
                Test my face
              </Button>
            )}

            {captureState === 'uploading' && (
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
                  Confidence: {(testResult.confidence * 100).toFixed(1)}% (threshold:{' '}
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
                cleanupThumbnails();
                setSamples([]);
                setThumbnails([]);
                setTestResult(null);
                setSuccessMessage(null);
              }}
            >
              Re-enroll face profile
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
