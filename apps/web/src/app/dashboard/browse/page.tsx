'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Globe,
  RefreshCw,
  Search,
  Eye,
  Shield,
  Clock,
  ExternalLink,
  Plus,
  Trash2,
  Loader2,
  Settings2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { MonitorCard } from '@/components/dashboard/monitor-card';
import { BrowseUrlDialog } from '@/components/dashboard/browse-url-dialog';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface BrowseLogEntry {
  id: string;
  url: string;
  title: string | null;
  summary: string | null;
  status_code: number | null;
  content_length: number;
  fetch_ms: number;
  error: string | null;
  created_at: string;
}

interface Monitor {
  id: string;
  url: string;
  keywords: string[];
  interval_hours: number;
  status: string;
  last_checked_at: string | null;
  last_triggered_at: string | null;
  trigger_reason: string | null;
  check_count: number;
  created_at: string;
}

interface DomainRule {
  id: string;
  domain: string;
  rule_type: string;
  created_at: string;
}

interface BrowseConfig {
  enabled: boolean;
  auto_summarize: boolean;
  max_pages_per_day: number;
}

interface SearchResultItem {
  title: string;
  url: string;
  snippet: string;
  summary: string | null;
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

// ─── Component ──────────────────────────────────────────

export default function BrowsePage() {
  const [tab, setTab] = useState<'history' | 'monitors' | 'search' | 'settings'>('history');
  const [history, setHistory] = useState<BrowseLogEntry[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [domainRules, setDomainRules] = useState<DomainRule[]>([]);
  const [config, setConfig] = useState<BrowseConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  // Add monitor state
  const [newMonitorUrl, setNewMonitorUrl] = useState('');
  const [newMonitorKeywords, setNewMonitorKeywords] = useState('');
  const [newMonitorInterval, setNewMonitorInterval] = useState('24');
  const [addingMonitor, setAddingMonitor] = useState(false);

  // Add domain rule state
  const [newDomain, setNewDomain] = useState('');
  const [newRuleType, setNewRuleType] = useState<'block' | 'allow'>('block');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [historyData, monitorsData, rulesData, configData] = await Promise.all([
        api.get<{ logs: BrowseLogEntry[]; total: number }>('/api/browse/history?limit=30'),
        api.get<{ monitors: Monitor[]; total: number }>('/api/browse/monitors'),
        api.get<{ rules: DomainRule[]; total: number }>('/api/browse/domains'),
        api.get<BrowseConfig>('/api/browse/config'),
      ]);
      setHistory(historyData.logs);
      setHistoryTotal(historyData.total);
      setMonitors(monitorsData.monitors);
      setDomainRules(rulesData.rules);
      setConfig(configData);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to load browse data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchResults([]);
    try {
      const data = await api.post<{ query: string; results: SearchResultItem[]; total: number }>(
        '/api/browse/search',
        { query: searchQuery, max_results: 10, summarize_top: 3 },
      );
      setSearchResults(data.results);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setSearching(false);
    }
  }

  async function handleAddMonitor(e: React.FormEvent) {
    e.preventDefault();
    if (!newMonitorUrl.trim()) return;
    setAddingMonitor(true);
    try {
      await api.post('/api/browse/monitors', {
        url: newMonitorUrl,
        keywords: newMonitorKeywords ? newMonitorKeywords.split(',').map((k) => k.trim()) : [],
        interval_hours: parseFloat(newMonitorInterval) || 24,
      });
      setNewMonitorUrl('');
      setNewMonitorKeywords('');
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setAddingMonitor(false);
    }
  }

  async function handleToggleMonitor(id: string, status: string) {
    try {
      await api.put(`/api/browse/monitors/${id}`, { status });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleDeleteMonitor(id: string) {
    try {
      await api.delete(`/api/browse/monitors/${id}`);
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleAddDomainRule(e: React.FormEvent) {
    e.preventDefault();
    if (!newDomain.trim()) return;
    try {
      await api.post('/api/browse/domains', {
        domain: newDomain,
        rule_type: newRuleType,
      });
      setNewDomain('');
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleDeleteDomainRule(id: string) {
    try {
      await api.delete(`/api/browse/domains/${id}`);
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleToggleEnabled() {
    if (!config) return;
    try {
      const data = await api.put<BrowseConfig>('/api/browse/config', {
        enabled: !config.enabled,
      });
      setConfig(data);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Globe className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Web Activity</h1>
            <p className="text-sm text-muted-foreground">
              Browse the web, search, and monitor pages for changes.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {config && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleEnabled}
              className={cn(!config.enabled && 'text-destructive')}
            >
              {config.enabled ? 'Enabled' : 'Disabled'}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </Button>
          <BrowseUrlDialog onBrowsed={fetchData} />
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Tab switcher */}
      <div className="flex gap-2">
        {(
          [
            { key: 'history', label: 'History', icon: Clock },
            { key: 'search', label: 'Search', icon: Search },
            { key: 'monitors', label: 'Monitors', icon: Eye },
            { key: 'settings', label: 'Settings', icon: Settings2 },
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
            {key === 'monitors' && monitors.length > 0 && (
              <Badge variant="secondary" className="ml-1.5 h-5 px-1.5 text-[10px]">
                {monitors.length}
              </Badge>
            )}
          </Button>
        ))}
      </div>

      {/* History tab */}
      {tab === 'history' && (
        <div className="space-y-2">
          {loading && history.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground">
              Loading history...
            </div>
          ) : history.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
              <Globe className="h-8 w-8" />
              <p>No browsing history yet.</p>
              <p className="text-xs">Click &quot;Browse URL&quot; to get started.</p>
            </div>
          ) : (
            history.map((log) => (
              <Card key={log.id}>
                <CardContent className="flex items-start justify-between p-4">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      {log.title ? (
                        <p className="text-sm font-medium truncate">{log.title}</p>
                      ) : (
                        <p className="text-sm text-muted-foreground truncate">{log.url}</p>
                      )}
                      {log.error && (
                        <Badge variant="destructive" className="text-[10px] shrink-0">
                          Error
                        </Badge>
                      )}
                    </div>
                    <a
                      href={log.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:underline truncate"
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" />
                      {log.url}
                    </a>
                    {log.summary && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {log.summary}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 ml-4 shrink-0">
                    <span className="text-[11px] text-muted-foreground">
                      {relativeTime(log.created_at)}
                    </span>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      {log.status_code && <span>{log.status_code}</span>}
                      <span>{log.fetch_ms}ms</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
          {historyTotal > history.length && (
            <p className="text-center text-xs text-muted-foreground">
              Showing {history.length} of {historyTotal} entries
            </p>
          )}
        </div>
      )}

      {/* Search tab */}
      {tab === 'search' && (
        <div className="space-y-4">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search the web..."
              className="flex-1"
            />
            <Button type="submit" disabled={searching || !searchQuery.trim()}>
              {searching ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-1.5 h-4 w-4" />
              )}
              Search
            </Button>
          </form>

          {searchResults.length > 0 && (
            <div className="space-y-2">
              {searchResults.map((result, i) => (
                <Card key={`${result.url}-${i}`}>
                  <CardContent className="p-4 space-y-1">
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-primary hover:underline"
                    >
                      {result.title}
                    </a>
                    <p className="text-xs text-muted-foreground truncate">{result.url}</p>
                    <p className="text-xs">{result.snippet}</p>
                    {result.summary && (
                      <div className="mt-2 rounded border bg-muted/50 p-2 text-xs">
                        <span className="font-medium text-muted-foreground">AI Summary: </span>
                        {result.summary}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {!searching && searchResults.length === 0 && searchQuery && (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              No results found. Try a different query.
            </div>
          )}
        </div>
      )}

      {/* Monitors tab */}
      {tab === 'monitors' && (
        <div className="space-y-4">
          {/* Add monitor form */}
          <Card>
            <CardContent className="p-4">
              <form onSubmit={handleAddMonitor} className="space-y-3">
                <div className="flex gap-2">
                  <Input
                    value={newMonitorUrl}
                    onChange={(e) => setNewMonitorUrl(e.target.value)}
                    placeholder="URL to monitor"
                    className="flex-1"
                  />
                  <Input
                    value={newMonitorKeywords}
                    onChange={(e) => setNewMonitorKeywords(e.target.value)}
                    placeholder="Keywords (comma-separated)"
                    className="flex-1"
                  />
                </div>
                <div className="flex items-end gap-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Interval (hours)</Label>
                    <Input
                      type="number"
                      min="0.5"
                      step="0.5"
                      value={newMonitorInterval}
                      onChange={(e) => setNewMonitorInterval(e.target.value)}
                      className="w-24"
                    />
                  </div>
                  <Button type="submit" disabled={addingMonitor || !newMonitorUrl.trim()}>
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    Add Monitor
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {monitors.length === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center gap-2 text-muted-foreground">
              <Eye className="h-6 w-6" />
              <p className="text-sm">No page monitors configured.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {monitors.map((m) => (
                <MonitorCard
                  key={m.id}
                  monitor={m}
                  onToggle={handleToggleMonitor}
                  onDelete={handleDeleteMonitor}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Settings tab */}
      {tab === 'settings' && config && (
        <div className="space-y-6">
          {/* Browse config */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Browsing Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={config.auto_summarize}
                  onChange={async () => {
                    const data = await api.put<BrowseConfig>('/api/browse/config', {
                      auto_summarize: !config.auto_summarize,
                    });
                    setConfig(data);
                  }}
                  className="h-4 w-4 rounded border-input"
                />
                <span className="text-sm">Auto-summarize fetched pages</span>
              </label>
              <div className="flex items-center gap-3">
                <Label className="text-sm">Max pages per day:</Label>
                <Input
                  type="number"
                  min="1"
                  max="500"
                  value={config.max_pages_per_day}
                  onChange={async (e) => {
                    const val = parseInt(e.target.value) || 50;
                    const data = await api.put<BrowseConfig>('/api/browse/config', {
                      max_pages_per_day: val,
                    });
                    setConfig(data);
                  }}
                  className="w-24"
                />
              </div>
            </CardContent>
          </Card>

          <Separator />

          {/* Domain rules */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Shield className="h-4 w-4" />
                Domain Rules
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={handleAddDomainRule} className="flex gap-2">
                <Input
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="example.com"
                  className="flex-1"
                />
                <div className="flex gap-1">
                  {(['block', 'allow'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setNewRuleType(t)}
                      className={cn(
                        'rounded-md border px-3 py-2 text-xs font-medium transition-colors',
                        newRuleType === t
                          ? t === 'block'
                            ? 'border-destructive bg-destructive text-destructive-foreground'
                            : 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background hover:bg-accent',
                      )}
                    >
                      {t === 'block' ? 'Block' : 'Allow'}
                    </button>
                  ))}
                </div>
                <Button type="submit" variant="outline" disabled={!newDomain.trim()}>
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </form>

              {domainRules.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No custom domain rules. Default malware and adult site blocking is active.
                </p>
              ) : (
                <div className="space-y-1">
                  {domainRules.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={rule.rule_type === 'block' ? 'destructive' : 'default'}
                          className="text-[10px]"
                        >
                          {rule.rule_type}
                        </Badge>
                        <span className="text-sm font-mono">{rule.domain}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteDomainRule(rule.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
