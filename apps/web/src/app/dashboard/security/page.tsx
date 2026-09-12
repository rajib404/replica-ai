'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Shield,
  Lock,
  KeyRound,
  Download,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  Eye,
  EyeOff,
  Copy,
  ScrollText,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface EncryptionStatus {
  master_key_configured: boolean;
  algorithm: string;
  kdf: string;
  kdf_iterations: number;
  encrypted_fields_count: number;
  encrypted_files_count: number;
  warning: string;
}

interface AuditLogEntry {
  id: string;
  action: string;
  category: string;
  outcome: string;
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

interface AuditLogResponse {
  entries: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

interface TwoFactorStatus {
  enabled: boolean;
  confirmed_at: string | null;
  last_used_at: string | null;
  backup_codes_remaining: number;
}

interface TwoFactorSetup {
  secret: string;
  provisioning_uri: string;
  qr_code_base64: string;
  backup_codes: string[];
}

interface DataExport {
  export_id: string;
  status: string;
  archive_size_bytes: number | null;
  archive_sha256: string | null;
  download_url: string | null;
  expires_at: string | null;
  created_at: string;
  completed_at: string | null;
}

// ─── Helpers ────────────────────────────────────────────

function formatBytes(n: number | null): string {
  if (!n) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(s: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleString();
}

function categoryColor(category: string): string {
  const map: Record<string, string> = {
    auth: 'bg-blue-500/10 text-blue-600',
    data_access: 'bg-green-500/10 text-green-600',
    settings: 'bg-purple-500/10 text-purple-600',
    external_api: 'bg-orange-500/10 text-orange-600',
    payment: 'bg-yellow-500/10 text-yellow-600',
    security: 'bg-red-500/10 text-red-600',
    admin: 'bg-gray-500/10 text-gray-600',
  };
  return map[category] ?? 'bg-gray-500/10 text-gray-600';
}

// ─── Page ───────────────────────────────────────────────

export default function SecurityPage() {
  const [encStatus, setEncStatus] = useState<EncryptionStatus | null>(null);
  const [twoFAStatus, setTwoFAStatus] = useState<TwoFactorStatus | null>(null);
  const [auditLog, setAuditLog] = useState<AuditLogResponse | null>(null);
  const [exports, setExports] = useState<DataExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [enc, tfa, log, exp] = await Promise.all([
        api.get<EncryptionStatus>('/api/security/encryption-status'),
        api.get<TwoFactorStatus>('/api/security/2fa/status'),
        api.get<AuditLogResponse>('/api/security/audit-log?page=1&page_size=20'),
        api.get<{ exports: DataExport[] }>('/api/security/export'),
      ]);
      setEncStatus(enc);
      setTwoFAStatus(tfa);
      setAuditLog(log);
      setExports(exp.exports);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load security data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading && !encStatus) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-7 w-7" /> Security
          </h1>
          <p className="text-muted-foreground mt-1">
            Manage encryption, two-factor auth, audit logs, and account data.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={cn('h-4 w-4 mr-2', loading && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-red-500/50">
          <CardContent className="pt-6 text-sm text-red-600">{error}</CardContent>
        </Card>
      )}

      <PasswordCard />
      {encStatus && <EncryptionCard status={encStatus} />}
      {twoFAStatus && <TwoFactorCard status={twoFAStatus} onChange={refresh} />}
      <DataExportCard exports={exports} onChange={refresh} />
      <AuditLogCard log={auditLog} />
      <DangerZoneCard onDeleted={refresh} twoFAEnabled={twoFAStatus?.enabled ?? false} />
    </div>
  );
}

// ─── Password ────────────────────────────────────────────

function PasswordCard() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await api.put<{ success: boolean; message: string }>('/api/auth/password', {
        current_password: currentPassword || null,
        new_password: newPassword,
      });
      setMessage({ text: res.message, ok: res.success });
      if (res.success) {
        setCurrentPassword('');
        setNewPassword('');
      }
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : 'Failed to update password', ok: false });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5" /> Password
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="current-password">Current password</Label>
            <Input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Leave blank if you haven't set one yet"
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
            />
          </div>
        </div>

        {message && (
          <p className={cn('text-xs', message.ok ? 'text-green-700' : 'text-red-600')}>
            {message.text}
          </p>
        )}

        <Button onClick={save} size="sm" disabled={saving || newPassword.trim().length < 8}>
          {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {currentPassword ? 'Change password' : 'Set password'}
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Encryption status ──────────────────────────────────

function EncryptionCard({ status }: { status: EncryptionStatus }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Lock className="h-5 w-5" /> Encryption at Rest
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center gap-2">
          {status.master_key_configured ? (
            <Badge className="bg-green-500/10 text-green-700">
              <CheckCircle2 className="h-3 w-3 mr-1" /> Configured
            </Badge>
          ) : (
            <Badge className="bg-red-500/10 text-red-700">
              <XCircle className="h-3 w-3 mr-1" /> Not configured
            </Badge>
          )}
          <span className="text-muted-foreground">Master key</span>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-muted-foreground">Algorithm</div>
            <div className="font-mono">{status.algorithm}</div>
          </div>
          <div>
            <div className="text-muted-foreground">KDF</div>
            <div className="font-mono">
              {status.kdf} ({status.kdf_iterations.toLocaleString()} iters)
            </div>
          </div>
        </div>
        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <p>{status.warning}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Two-factor authentication ──────────────────────────

function TwoFactorCard({
  status,
  onChange,
}: {
  status: TwoFactorStatus;
  onChange: () => void;
}) {
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');

  const startSetup = async () => {
    setMessage(null);
    try {
      const res = await api.post<TwoFactorSetup>('/api/security/2fa/setup');
      setSetup(res);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Setup failed');
    }
  };

  const verify = async () => {
    setVerifying(true);
    setMessage(null);
    try {
      const res = await api.post<{ verified: boolean; message: string }>(
        '/api/security/2fa/verify',
        { code },
      );
      setMessage(res.message);
      if (res.verified) {
        setSetup(null);
        setCode('');
        onChange();
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Verification failed');
    } finally {
      setVerifying(false);
    }
  };

  const disable = async () => {
    setMessage(null);
    try {
      const res = await api.post<{ verified: boolean; message: string }>(
        '/api/security/2fa/disable',
        { password: disablePassword },
      );
      setMessage(res.message);
      if (res.verified) {
        setDisablePassword('');
        onChange();
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Disable failed');
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5" /> Two-Factor Authentication
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex items-center gap-2">
          {status.enabled ? (
            <Badge className="bg-green-500/10 text-green-700">
              <CheckCircle2 className="h-3 w-3 mr-1" /> Enabled
            </Badge>
          ) : (
            <Badge className="bg-gray-500/10 text-gray-700">
              <XCircle className="h-3 w-3 mr-1" /> Disabled
            </Badge>
          )}
          {status.enabled && status.last_used_at && (
            <span className="text-xs text-muted-foreground">
              Last used: {formatDate(status.last_used_at)}
            </span>
          )}
          {status.enabled && (
            <span className="text-xs text-muted-foreground">
              · {status.backup_codes_remaining} backup codes left
            </span>
          )}
        </div>

        {!status.enabled && !setup && (
          <Button onClick={startSetup} size="sm">
            Set up 2FA
          </Button>
        )}

        {setup && (
          <div className="space-y-3 rounded-md border p-4">
            <p className="text-xs text-muted-foreground">
              Scan this QR code in your authenticator app, then enter the 6-digit code below.
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/png;base64,${setup.qr_code_base64}`}
              alt="2FA QR code"
              className="h-48 w-48 border rounded"
            />
            <div className="flex items-center gap-2">
              <code className="text-xs font-mono px-2 py-1 rounded bg-muted">
                {showSecret ? setup.secret : '••••••••••••'}
              </code>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSecret((v) => !v)}
              >
                {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigator.clipboard.writeText(setup.secret)}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-medium text-amber-700">
                Backup codes (save these now — shown only once)
              </Label>
              <div className="grid grid-cols-2 gap-1 text-xs font-mono">
                {setup.backup_codes.map((c) => (
                  <code key={c} className="px-2 py-1 rounded bg-muted">
                    {c}
                  </code>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <Input
                placeholder="6-digit code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={10}
                className="font-mono w-32"
              />
              <Button onClick={verify} disabled={verifying || !code} size="sm">
                {verifying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Verify & Enable
              </Button>
            </div>
          </div>
        )}

        {status.enabled && (
          <div className="space-y-2">
            <Label className="text-xs">Disable 2FA (requires password)</Label>
            <div className="flex gap-2">
              <Input
                type="password"
                placeholder="Your password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                className="max-w-xs"
              />
              <Button onClick={disable} variant="outline" size="sm">
                Disable
              </Button>
            </div>
          </div>
        )}

        {message && <p className="text-xs text-muted-foreground">{message}</p>}
      </CardContent>
    </Card>
  );
}

// ─── Data export ────────────────────────────────────────

function DataExportCard({
  exports,
  onChange,
}: {
  exports: DataExport[];
  onChange: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      await api.post('/api/security/export');
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setCreating(false);
    }
  };

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Download className="h-5 w-5" /> Data Export
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Download an encrypted archive of all your data. Archives expire after 48 hours.
        </p>
        <Button onClick={create} disabled={creating} size="sm">
          {creating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Create new export
        </Button>
        {error && <p className="text-xs text-red-600">{error}</p>}

        {exports.length > 0 && (
          <div className="space-y-1 mt-3">
            {exports.map((exp) => (
              <div
                key={exp.export_id}
                className="flex items-center justify-between rounded border px-3 py-2 text-xs"
              >
                <div>
                  <div className="font-mono">{exp.export_id}</div>
                  <div className="text-muted-foreground">
                    {formatDate(exp.created_at)} · {formatBytes(exp.archive_size_bytes)} ·{' '}
                    <span
                      className={cn(
                        exp.status === 'ready' && 'text-green-600',
                        exp.status === 'failed' && 'text-red-600',
                      )}
                    >
                      {exp.status}
                    </span>
                  </div>
                </div>
                {exp.status === 'ready' && exp.download_url && (
                  <a
                    href={`${apiBase}${exp.download_url}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    Download
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Audit log ──────────────────────────────────────────

function AuditLogCard({ log }: { log: AuditLogResponse | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScrollText className="h-5 w-5" /> Audit Log
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {!log || log.entries.length === 0 ? (
          <p className="text-xs text-muted-foreground">No audit events recorded yet.</p>
        ) : (
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {log.entries.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between rounded border px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Badge className={cn(categoryColor(entry.category), 'shrink-0')}>
                    {entry.category}
                  </Badge>
                  <span className="font-mono truncate">{entry.action}</span>
                  {entry.outcome !== 'success' && (
                    <Badge className="bg-red-500/10 text-red-700 shrink-0">
                      {entry.outcome}
                    </Badge>
                  )}
                </div>
                <div className="text-muted-foreground shrink-0 ml-4">
                  {formatDate(entry.created_at)}
                </div>
              </div>
            ))}
            <div className="pt-2 text-xs text-muted-foreground">
              Showing {log.entries.length} of {log.total} entries
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Danger zone ────────────────────────────────────────

function DangerZoneCard({
  onDeleted,
  twoFAEnabled,
}: {
  onDeleted: () => void;
  twoFAEnabled: boolean;
}) {
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const REQUIRED_PHRASE = 'DELETE MY ACCOUNT';

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/security/delete-all', {
        confirm_phrase: confirmPhrase,
        password,
        totp_code: totpCode || null,
      });
      onDeleted();
      // Clear local tokens
      api.clearTokens();
      window.location.href = '/';
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deletion failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-red-500/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-red-600">
          <Trash2 className="h-5 w-5" /> Danger Zone
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Permanently delete your account and all associated data. This cannot be undone.
        </p>
        {!confirming ? (
          <Button
            variant="outline"
            size="sm"
            className="border-red-500/60 text-red-600 hover:bg-red-500/10"
            onClick={() => setConfirming(true)}
          >
            Delete my account
          </Button>
        ) : (
          <div className="space-y-3 rounded border border-red-500/40 p-4">
            <div>
              <Label className="text-xs">
                Type <code className="font-mono">{REQUIRED_PHRASE}</code> to confirm
              </Label>
              <Input
                value={confirmPhrase}
                onChange={(e) => setConfirmPhrase(e.target.value)}
                className="font-mono mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Password</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1"
              />
            </div>
            {twoFAEnabled && (
              <div>
                <Label className="text-xs">2FA code</Label>
                <Input
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  maxLength={10}
                  className="font-mono mt-1 max-w-xs"
                />
              </div>
            )}
            {error && <p className="text-xs text-red-600">{error}</p>}
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="border-red-500/60 text-red-600 hover:bg-red-500/10"
                onClick={submit}
                disabled={busy || confirmPhrase !== REQUIRED_PHRASE || !password}
              >
                {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Permanently delete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setConfirming(false);
                  setConfirmPhrase('');
                  setPassword('');
                  setTotpCode('');
                  setError(null);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
