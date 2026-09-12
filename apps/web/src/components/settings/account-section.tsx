'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { User, KeyRound, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

interface ProfileResponse {
  owner_id: string;
  name: string;
  email: string;
  phone: string | null;
  preferred_language: string;
  has_password: boolean;
  google_linked: boolean;
}

export function AccountSection() {
  return (
    <>
      <ProfileForm />
      <PasswordForm />
    </>
  );
}

function ProfileForm() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [googleLinked, setGoogleLinked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const profile = await api.get<ProfileResponse>('/api/auth/me');
        setName(profile.name);
        setEmail(profile.email);
        setPhone(profile.phone ?? '');
        setGoogleLinked(profile.google_linked);
      } catch (err) {
        setError(err instanceof api.ApiError ? err.detail : 'Failed to load profile');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const profile = await api.put<ProfileResponse>('/api/auth/profile', {
        name,
        email,
        phone: phone.trim() || null,
      });
      setName(profile.name);
      setEmail(profile.email);
      setPhone(profile.phone ?? '');
      if (typeof window !== 'undefined') {
        localStorage.setItem('owner_name', profile.name);
      }
      setSuccessMessage('Profile updated');
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <User className="h-5 w-5" />
          Account
        </CardTitle>
        <CardDescription>Your name, email, and phone number.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading profile...
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
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

            <div className="space-y-2">
              <Label htmlFor="account-name">Name</Label>
              <Input
                id="account-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                minLength={1}
                maxLength={100}
                disabled={saving}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="account-email">Email</Label>
              <Input
                id="account-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={saving}
              />
              {googleLinked && (
                <p className="text-xs text-muted-foreground">
                  Your Google account is linked — signing in with Google will still work after
                  you change this.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="account-phone">Phone (optional)</Label>
              <Input
                id="account-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={saving}
              />
            </div>

            <Button type="submit" disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save changes'
              )}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function PasswordForm() {
  const [hasPassword, setHasPassword] = useState<boolean | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const profile = await api.get<ProfileResponse>('/api/auth/me');
        setHasPassword(profile.has_password);
      } catch {
        setHasPassword(false);
      }
    })();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setSaving(true);
    try {
      const resp = await api.put<{ success: boolean; message: string }>('/api/auth/password', {
        new_password: newPassword,
        current_password: hasPassword ? currentPassword : null,
      });
      if (resp.success) {
        setSuccessMessage(resp.message);
        setHasPassword(true);
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        setError(resp.message);
      }
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to update password');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <KeyRound className="h-5 w-5" />
          Password
        </CardTitle>
        <CardDescription>
          {hasPassword
            ? 'Change the password used to sign in.'
            : 'Set a password so you can sign in with your email, not just Google.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasPassword === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading...
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
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

            {hasPassword && (
              <div className="space-y-2">
                <Label htmlFor="current-password">Current password</Label>
                <Input
                  id="current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  disabled={saving}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                disabled={saving}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm new password</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                disabled={saving}
              />
            </div>

            <Button type="submit" disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : hasPassword ? (
                'Change password'
              ) : (
                'Set password'
              )}
            </Button>

            {hasPassword && (
              <Badge variant="secondary" className="gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Password set
              </Badge>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}
