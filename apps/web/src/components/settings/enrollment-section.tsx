'use client';

import dynamic from 'next/dynamic';

const VoiceEnrollment = dynamic(
  () => import('./voice-enrollment').then((mod) => ({ default: mod.VoiceEnrollment })),
  {
    ssr: false,
    loading: () => (
      <div className="h-48 animate-pulse rounded-xl border bg-card" aria-hidden />
    ),
  },
);

const FaceEnrollment = dynamic(
  () => import('./face-enrollment').then((mod) => ({ default: mod.FaceEnrollment })),
  {
    ssr: false,
    loading: () => (
      <div className="h-48 animate-pulse rounded-xl border bg-card" aria-hidden />
    ),
  },
);

export function EnrollmentSection() {
  return (
    <>
      <VoiceEnrollment />
      <FaceEnrollment />
    </>
  );
}
