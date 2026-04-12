'use client';

import { useState } from 'react';
import {
  Shield,
  ShieldCheck,
  ShieldOff,
  Trash2,
  Link2,
  Copy,
  Check,
  QrCode,
} from 'lucide-react';
import type { AccessRule } from '@replica-ai/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

const ACCESS_COLORS: Record<string, string> = {
  full: 'bg-green-500/15 text-green-700 border-green-500/25',
  read_only: 'bg-blue-500/15 text-blue-700 border-blue-500/25',
  limited: 'bg-orange-500/15 text-orange-700 border-orange-500/25',
};

const VERIFICATION_LABELS: Record<string, string> = {
  secret_word: 'Secret Word',
  secret_event: 'Secret Event',
  voice_match: 'Voice Match',
  face_match: 'Face Match',
  none: 'None',
};

interface InviteResult {
  invite_id: string;
  invite_url: string;
  invite_token: string;
  qr_code_base64: string;
  is_reusable: boolean;
  uses_remaining: number;
  expires_at: string;
}

interface RuleCardProps {
  rule: AccessRule;
  onToggle: (id: string, active: boolean) => void;
  onDelete: (id: string) => void;
}

export function RuleCard({ rule, onToggle, onDelete }: RuleCardProps) {
  const [invite, setInvite] = useState<InviteResult | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showQr, setShowQr] = useState(false);

  const AccessIcon = rule.isActive ? ShieldCheck : ShieldOff;

  async function handleGenerateInvite() {
    setInviteLoading(true);
    try {
      const data = await api.post<InviteResult>(`/api/access/invite/${rule.id}`, {
        is_reusable: false,
        max_uses: 1,
      });
      setInvite(data);
    } catch {
      // silently ignore — user can retry
    } finally {
      setInviteLoading(false);
    }
  }

  async function copyLink() {
    if (!invite) return;
    await navigator.clipboard.writeText(invite.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card className={cn(!rule.isActive && 'opacity-60')}>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <AccessIcon className={cn('h-5 w-5', rule.isActive ? 'text-green-600' : 'text-muted-foreground')} />
          <div>
            <CardTitle className="text-base">{rule.granteeName}</CardTitle>
            {rule.granteeRelation && (
              <p className="text-xs text-muted-foreground capitalize">{rule.granteeRelation.replace('_', ' ')}</p>
            )}
          </div>
        </div>
        <Badge className={cn('capitalize', ACCESS_COLORS[rule.accessLevel] ?? '')}>
          {rule.accessLevel.replace('_', ' ')}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="text-xs">
            <Shield className="mr-1 h-3 w-3" />
            {VERIFICATION_LABELS[rule.verificationMethod] ?? rule.verificationMethod}
          </Badge>
          {rule.templateName && (
            <Badge variant="secondary" className="text-xs">
              {rule.templateName.replace('_', ' ')}
            </Badge>
          )}
        </div>

        {rule.topicRestrictions && (
          <div className="space-y-1">
            {rule.topicRestrictions.allowed.length > 0 && (
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-green-700">Allowed:</span>{' '}
                {rule.topicRestrictions.allowed.join(', ')}
              </p>
            )}
            {rule.topicRestrictions.blocked.length > 0 && (
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-red-700">Blocked:</span>{' '}
                {rule.topicRestrictions.blocked.join(', ')}
              </p>
            )}
          </div>
        )}

        {rule.validUntil && (
          <p className="text-xs text-muted-foreground">
            Expires: {new Date(rule.validUntil).toLocaleDateString()}
          </p>
        )}

        {/* Invite section */}
        {invite && (
          <div className="rounded-md border bg-muted/50 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate text-xs">{invite.invite_url}</code>
              <Button variant="outline" size="icon" className="h-7 w-7" onClick={copyLink}>
                {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => setShowQr((v) => !v)}
              >
                <QrCode className="h-3 w-3" />
              </Button>
            </div>
            {showQr && (
              <div className="flex justify-center">
                <img
                  src={`data:image/png;base64,${invite.qr_code_base64}`}
                  alt="QR Code"
                  className="h-32 w-32"
                />
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Expires: {new Date(invite.expires_at).toLocaleString()}
            </p>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          {rule.isActive && !invite && (
            <Button variant="outline" size="sm" onClick={handleGenerateInvite} disabled={inviteLoading}>
              <Link2 className="mr-1.5 h-3.5 w-3.5" />
              {inviteLoading ? 'Generating...' : 'Generate Invite'}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onToggle(rule.id, !rule.isActive)}
          >
            {rule.isActive ? 'Deactivate' : 'Activate'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onDelete(rule.id)}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
