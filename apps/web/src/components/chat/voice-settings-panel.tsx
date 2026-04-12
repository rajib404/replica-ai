'use client';

import { useEffect, useState } from 'react';
import { Settings2, Volume2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { api } from '@/lib/api';

interface VoiceInfo {
  voice_id: string;
  name: string;
  language: string;
  gender: string | null;
  description: string | null;
}

interface VoiceSettingsData {
  voice_id: string;
  speed: number;
  auto_play: boolean;
  output_format: string;
}

export function VoiceSettingsPanel() {
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [settings, setSettings] = useState<VoiceSettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<{ voices: VoiceInfo[] }>('/api/voice/voices'),
      api.get<VoiceSettingsData>('/api/voice/settings'),
    ])
      .then(([voicesResp, settingsResp]) => {
        setVoices(voicesResp.voices);
        setSettings(settingsResp);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function updateSetting(updates: Partial<VoiceSettingsData>) {
    if (!settings) return;
    setSaving(true);
    try {
      const resp = await api.put<VoiceSettingsData>('/api/voice/settings', updates);
      setSettings(resp);
    } catch {
      // Silently fail
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Settings2 className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Volume2 className="h-4 w-4" />
            Voice Settings
          </SheetTitle>
          <SheetDescription>Configure voice chat preferences.</SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : settings ? (
          <div className="mt-6 space-y-6">
            {/* Voice selection */}
            <div className="space-y-2">
              <Label>Output Voice</Label>
              <Select
                value={settings.voice_id}
                onValueChange={(v) => updateSetting({ voice_id: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {voices.map((v) => (
                    <SelectItem key={v.voice_id} value={v.voice_id}>
                      <span>{v.name}</span>
                      {v.gender && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({v.gender})
                        </span>
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {voices.find((v) => v.voice_id === settings.voice_id)?.description && (
                <p className="text-xs text-muted-foreground">
                  {voices.find((v) => v.voice_id === settings.voice_id)?.description}
                </p>
              )}
            </div>

            {/* Speed */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Speed</Label>
                <span className="text-sm text-muted-foreground">{settings.speed.toFixed(1)}x</span>
              </div>
              <Slider
                value={[settings.speed]}
                min={0.5}
                max={2.0}
                step={0.1}
                onValueCommit={([v]) => updateSetting({ speed: v })}
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>0.5x</span>
                <span>1.0x</span>
                <span>2.0x</span>
              </div>
            </div>

            {/* Auto-play */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-Play Responses</Label>
                <p className="text-xs text-muted-foreground">
                  Automatically play TTS audio when response is ready.
                </p>
              </div>
              <Switch
                checked={settings.auto_play}
                onCheckedChange={(v) => updateSetting({ auto_play: v })}
              />
            </div>

            {/* Output format */}
            <div className="space-y-2">
              <Label>Audio Format</Label>
              <Select
                value={settings.output_format}
                onValueChange={(v) => updateSetting({ output_format: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mp3">MP3 (smaller files)</SelectItem>
                  <SelectItem value="wav">WAV (higher quality)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {saving && (
              <p className="text-xs text-muted-foreground">Saving...</p>
            )}
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Failed to load voice settings.
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}
