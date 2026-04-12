'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  CreditCard,
  DollarSign,
  RefreshCw,
  Shield,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Lightbulb,
  Heart,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface BillingStatus {
  has_payment_method: boolean;
  card_last_four: string | null;
  card_brand: string | null;
  auto_pay_hosting: boolean;
  auto_pay_llm: boolean;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  hosting_expires_at: string | null;
  days_until_expiry: number | null;
  survival_mode: boolean;
  survival_mode_entered_at: string | null;
  last_payment_at: string | null;
}

interface HostingStatus {
  status: string;
  days_until_expiry: number | null;
  monthly_cost: number;
  is_auto_pay_active: boolean;
  survival_mode: boolean;
  survival_days_remaining: number | null;
}

interface PaymentLogEntry {
  id: string;
  amount_usd: number;
  currency: string;
  description: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

interface CostBreakdown {
  hosting_monthly_usd: number;
  llm_monthly_usd: number;
  storage_monthly_usd: number;
  total_monthly_usd: number;
  projected_annual_usd: number;
  suggestions: string[];
}

interface SurvivalConfig {
  grace_period_days: number;
  notify_family: boolean;
  weekly_reminders: boolean;
  never_shutdown_with_family: boolean;
}

// ─── Helpers ────────────────────────────────────────────

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function statusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'text-green-600';
    case 'expiring':
      return 'text-yellow-600';
    case 'expired':
      return 'text-red-600';
    case 'survival':
      return 'text-orange-600';
    default:
      return 'text-muted-foreground';
  }
}

function paymentStatusBadge(status: string) {
  switch (status) {
    case 'succeeded':
      return <Badge className="bg-green-100 text-green-700 text-[10px]">Paid</Badge>;
    case 'failed':
      return <Badge variant="destructive" className="text-[10px]">Failed</Badge>;
    case 'pending':
      return <Badge variant="secondary" className="text-[10px]">Pending</Badge>;
    case 'refunded':
      return <Badge variant="outline" className="text-[10px]">Refunded</Badge>;
    default:
      return <Badge variant="secondary" className="text-[10px]">{status}</Badge>;
  }
}

// ─── Component ──────────────────────────────────────────

export default function BillingPage() {
  const [tab, setTab] = useState<'overview' | 'payments' | 'survival'>('overview');
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [hosting, setHosting] = useState<HostingStatus | null>(null);
  const [costs, setCosts] = useState<CostBreakdown | null>(null);
  const [payments, setPayments] = useState<PaymentLogEntry[]>([]);
  const [paymentsTotal, setPaymentsTotal] = useState(0);
  const [survivalConfig, setSurvivalConfig] = useState<SurvivalConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Payment setup state
  const [paymentMethodId, setPaymentMethodId] = useState('');
  const [settingUp, setSettingUp] = useState(false);
  const [subscribing, setSubscribing] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [billingData, hostingData, costsData, paymentsData, survivalData] =
        await Promise.all([
          api.get<BillingStatus>('/api/billing/status'),
          api.get<HostingStatus>('/api/billing/hosting'),
          api.get<CostBreakdown>('/api/billing/costs'),
          api.get<{ payments: PaymentLogEntry[]; total: number }>('/api/billing/payments'),
          api.get<SurvivalConfig>('/api/billing/survival'),
        ]);
      setBilling(billingData);
      setHosting(hostingData);
      setCosts(costsData);
      setPayments(paymentsData.payments);
      setPaymentsTotal(paymentsData.total);
      setSurvivalConfig(survivalData);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to load billing data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleSetupBilling(e: React.FormEvent) {
    e.preventDefault();
    if (!paymentMethodId.trim()) return;
    setSettingUp(true);
    setError('');
    try {
      await api.post('/api/billing/setup', {
        payment_method_id: paymentMethodId,
      });
      setPaymentMethodId('');
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setSettingUp(false);
    }
  }

  async function handleSubscribe() {
    setSubscribing(true);
    setError('');
    try {
      await api.post('/api/billing/subscribe', {});
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setSubscribing(false);
    }
  }

  async function handleCancelSubscription() {
    setError('');
    try {
      await api.post('/api/billing/cancel', {});
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleToggleAutoPay(field: 'auto_pay_hosting' | 'auto_pay_llm') {
    if (!billing) return;
    try {
      await api.put('/api/billing/auto-pay', {
        [field]: !billing[field],
      });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleUpdateSurvival(updates: Partial<SurvivalConfig>) {
    try {
      const data = await api.put<SurvivalConfig>('/api/billing/survival', updates);
      setSurvivalConfig(data);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  if (loading && !billing) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <DollarSign className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Billing & Hosting</h1>
            <p className="text-sm text-muted-foreground">
              Manage payments, hosting, and self-preservation settings.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
          <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {/* Survival mode banner */}
      {billing?.survival_mode && (
        <div className="rounded-lg border border-orange-300 bg-orange-50 p-4 dark:border-orange-700 dark:bg-orange-950">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-orange-600 shrink-0" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-orange-800 dark:text-orange-300">
                Survival Mode Active
              </p>
              <p className="text-xs text-orange-700 dark:text-orange-400">
                Payment has failed. External LLM and web browsing are disabled to reduce costs.
                {hosting?.survival_days_remaining != null && (
                  <span className="font-medium">
                    {' '}
                    {hosting.survival_days_remaining} days remaining in grace period.
                  </span>
                )}
              </p>
              {billing.has_payment_method && (
                <Button
                  size="sm"
                  className="mt-2"
                  onClick={handleSubscribe}
                  disabled={subscribing}
                >
                  {subscribing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  Retry Payment
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Tab switcher */}
      <div className="flex gap-2">
        {(
          [
            { key: 'overview', label: 'Overview', icon: TrendingUp },
            { key: 'payments', label: 'Payments', icon: CreditCard },
            { key: 'survival', label: 'Self-Preservation', icon: Heart },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <Button
            key={key}
            variant={tab === key ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTab(key)}
          >
            <Icon className="mr-1.5 h-3.5 w-3.5" />
            {label}
          </Button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          {/* Hosting status */}
          {hosting && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between text-base">
                  <span>Hosting Status</span>
                  <Badge
                    variant="outline"
                    className={cn('capitalize', statusColor(hosting.status))}
                  >
                    {hosting.status}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Monthly Cost</p>
                    <p className="text-lg font-semibold">${hosting.monthly_cost.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Expires In</p>
                    <p className="text-lg font-semibold">
                      {hosting.days_until_expiry != null
                        ? `${hosting.days_until_expiry} days`
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Auto-Pay</p>
                    <p className="text-lg font-semibold">
                      {hosting.is_auto_pay_active ? 'On' : 'Off'}
                    </p>
                  </div>
                </div>
                {billing?.hosting_expires_at && (
                  <p className="text-xs text-muted-foreground">
                    Next renewal: {formatDate(billing.hosting_expires_at)}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Cost breakdown */}
          {costs && (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-4">
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-xs text-muted-foreground">Hosting</p>
                    <p className="text-xl font-bold">${costs.hosting_monthly_usd.toFixed(2)}</p>
                    <p className="text-[10px] text-muted-foreground">/month</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-xs text-muted-foreground">External LLM</p>
                    <p className="text-xl font-bold">${costs.llm_monthly_usd.toFixed(2)}</p>
                    <p className="text-[10px] text-muted-foreground">/month</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-xs text-muted-foreground">Storage</p>
                    <p className="text-xl font-bold">${costs.storage_monthly_usd.toFixed(2)}</p>
                    <p className="text-[10px] text-muted-foreground">/month</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-xs text-muted-foreground">Total</p>
                    <p className="text-xl font-bold text-primary">
                      ${costs.total_monthly_usd.toFixed(2)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      ~${costs.projected_annual_usd.toFixed(0)}/yr
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Suggestions */}
              {costs.suggestions.length > 0 && (
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-2">
                      <Lightbulb className="mt-0.5 h-4 w-4 text-yellow-500 shrink-0" />
                      <div className="space-y-1">
                        {costs.suggestions.map((s, i) => (
                          <p key={i} className="text-xs text-muted-foreground">
                            {s}
                          </p>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          <Separator />

          {/* Payment method */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <CreditCard className="h-4 w-4" />
                Payment Method
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {billing?.has_payment_method ? (
                <div className="flex items-center justify-between rounded-md border p-3">
                  <div className="flex items-center gap-3">
                    <CreditCard className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium capitalize">
                        {billing.card_brand ?? 'Card'} ending in {billing.card_last_four}
                      </p>
                      {billing.last_payment_at && (
                        <p className="text-xs text-muted-foreground">
                          Last payment: {relativeTime(billing.last_payment_at)}
                        </p>
                      )}
                    </div>
                  </div>
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No payment method on file.</p>
              )}

              <form onSubmit={handleSetupBilling} className="flex gap-2">
                <Input
                  value={paymentMethodId}
                  onChange={(e) => setPaymentMethodId(e.target.value)}
                  placeholder="Stripe Payment Method ID (pm_...)"
                  className="flex-1 font-mono text-xs"
                />
                <Button type="submit" variant="outline" disabled={settingUp || !paymentMethodId.trim()}>
                  {settingUp && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  {billing?.has_payment_method ? 'Update' : 'Add Card'}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Subscription / Auto-pay */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Subscription & Auto-Pay</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {billing?.stripe_subscription_id ? (
                <div className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <p className="text-sm font-medium">Active Subscription</p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {billing.stripe_subscription_id}
                    </p>
                  </div>
                  <Button variant="destructive" size="sm" onClick={handleCancelSubscription}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <p className="text-sm font-medium">No Active Subscription</p>
                    <p className="text-xs text-muted-foreground">
                      Subscribe for automatic monthly hosting renewal.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={handleSubscribe}
                    disabled={subscribing || !billing?.has_payment_method}
                  >
                    {subscribing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                    Subscribe
                  </Button>
                </div>
              )}

              <Separator />

              <div className="space-y-3">
                <label className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Auto-Pay Hosting</p>
                    <p className="text-xs text-muted-foreground">
                      Automatically renew hosting when it expires.
                    </p>
                  </div>
                  <button
                    onClick={() => handleToggleAutoPay('auto_pay_hosting')}
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                      billing?.auto_pay_hosting ? 'bg-primary' : 'bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        billing?.auto_pay_hosting ? 'translate-x-6' : 'translate-x-1',
                      )}
                    />
                  </button>
                </label>

                <label className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Auto-Pay External LLM</p>
                    <p className="text-xs text-muted-foreground">
                      Automatically pay for external LLM usage.
                    </p>
                  </div>
                  <button
                    onClick={() => handleToggleAutoPay('auto_pay_llm')}
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                      billing?.auto_pay_llm ? 'bg-primary' : 'bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        billing?.auto_pay_llm ? 'translate-x-6' : 'translate-x-1',
                      )}
                    />
                  </button>
                </label>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Payments tab */}
      {tab === 'payments' && (
        <div className="space-y-2">
          {payments.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
              <CreditCard className="h-8 w-8" />
              <p>No payment history yet.</p>
            </div>
          ) : (
            <>
              {payments.map((p) => (
                <Card key={p.id}>
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{p.description}</p>
                        {paymentStatusBadge(p.status)}
                      </div>
                      {p.error_message && (
                        <p className="text-xs text-destructive">{p.error_message}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {formatDate(p.created_at)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p
                        className={cn(
                          'text-lg font-semibold',
                          p.status === 'failed' ? 'text-destructive' : '',
                        )}
                      >
                        ${p.amount_usd.toFixed(2)}
                      </p>
                      <p className="text-[10px] text-muted-foreground uppercase">
                        {p.currency}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {paymentsTotal > payments.length && (
                <p className="text-center text-xs text-muted-foreground">
                  Showing {payments.length} of {paymentsTotal} payments
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* Survival / Self-Preservation tab */}
      {tab === 'survival' && survivalConfig && (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Shield className="h-4 w-4" />
                Self-Preservation Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <p className="text-xs text-muted-foreground">
                Configure how your replica behaves when payments fail and it enters survival mode.
              </p>

              {/* Grace period */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  Grace Period (days)
                </Label>
                <p className="text-xs text-muted-foreground">
                  How many days to wait in survival mode before considering shutdown.
                </p>
                <Input
                  type="number"
                  min="7"
                  max="365"
                  value={survivalConfig.grace_period_days}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    if (val >= 7 && val <= 365) {
                      handleUpdateSurvival({ grace_period_days: val });
                    }
                  }}
                  className="w-32"
                />
              </div>

              <Separator />

              {/* Toggle options */}
              <div className="space-y-4">
                <label className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Notify Family Members</p>
                    <p className="text-xs text-muted-foreground">
                      Alert family members when entering survival mode.
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      handleUpdateSurvival({
                        notify_family: !survivalConfig.notify_family,
                      })
                    }
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                      survivalConfig.notify_family ? 'bg-primary' : 'bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        survivalConfig.notify_family ? 'translate-x-6' : 'translate-x-1',
                      )}
                    />
                  </button>
                </label>

                <label className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Weekly Reminders</p>
                    <p className="text-xs text-muted-foreground">
                      Send weekly reminders during survival mode.
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      handleUpdateSurvival({
                        weekly_reminders: !survivalConfig.weekly_reminders,
                      })
                    }
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                      survivalConfig.weekly_reminders ? 'bg-primary' : 'bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        survivalConfig.weekly_reminders ? 'translate-x-6' : 'translate-x-1',
                      )}
                    />
                  </button>
                </label>

                <label className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Never Shutdown with Family</p>
                    <p className="text-xs text-muted-foreground">
                      Keep running indefinitely as long as family members have active access, even
                      if the grace period expires.
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      handleUpdateSurvival({
                        never_shutdown_with_family:
                          !survivalConfig.never_shutdown_with_family,
                      })
                    }
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                      survivalConfig.never_shutdown_with_family ? 'bg-primary' : 'bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        survivalConfig.never_shutdown_with_family
                          ? 'translate-x-6'
                          : 'translate-x-1',
                      )}
                    />
                  </button>
                </label>
              </div>
            </CardContent>
          </Card>

          {/* Current survival status */}
          {billing?.survival_mode && (
            <Card className="border-orange-300 dark:border-orange-700">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base text-orange-700 dark:text-orange-400">
                  <Clock className="h-4 w-4" />
                  Current Survival Status
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Entered Survival</p>
                    <p className="text-sm font-medium">
                      {billing.survival_mode_entered_at
                        ? formatDate(billing.survival_mode_entered_at)
                        : 'Unknown'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Days Remaining</p>
                    <p className="text-sm font-semibold text-orange-600">
                      {hosting?.survival_days_remaining ?? 'N/A'}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  Web browsing and external LLM providers have been disabled to conserve resources.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
