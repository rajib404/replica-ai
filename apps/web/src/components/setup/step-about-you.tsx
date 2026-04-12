'use client';

import { useState, useMemo } from 'react';
import { ChevronDown, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LANGUAGES } from '@/lib/languages';
import type { SetupData } from '@/components/setup/setup-wizard';

interface StepAboutYouProps {
  data: SetupData;
  onChange: (partial: Partial<SetupData>) => void;
  onBack: () => void;
  onNext: () => void;
}

export function StepAboutYou({ data, onChange, onBack, onNext }: StepAboutYouProps) {
  const [langOpen, setLangOpen] = useState(false);
  const [langSearch, setLangSearch] = useState('');

  const filteredLanguages = useMemo(() => {
    if (!langSearch) return LANGUAGES;
    const q = langSearch.toLowerCase();
    return LANGUAGES.filter(
      (l) => l.name.toLowerCase().includes(q) || l.code.toLowerCase().includes(q),
    );
  }, [langSearch]);

  const selectedLang = LANGUAGES.find((l) => l.code === data.preferredLanguage);

  const isValid = data.name.trim().length > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-xl font-bold">About You</h2>
        <p className="text-sm text-muted-foreground">
          Tell us a bit about yourself so your Replica knows who it represents.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name *</Label>
          <Input
            id="name"
            placeholder="What should your Replica call you?"
            value={data.name}
            onChange={(e) => onChange({ name: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email (optional)</Label>
          <Input
            id="email"
            type="email"
            placeholder="For account recovery"
            value={data.email}
            onChange={(e) => onChange({ email: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <Label>Preferred Language</Label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setLangOpen(!langOpen)}
              className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span>{selectedLang?.name ?? 'Select language'}</span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </button>

            {langOpen && (
              <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg">
                <div className="flex items-center border-b px-3">
                  <Search className="h-4 w-4 shrink-0 opacity-50" />
                  <input
                    className="flex h-10 w-full bg-transparent px-2 py-3 text-sm outline-none placeholder:text-muted-foreground"
                    placeholder="Search languages..."
                    value={langSearch}
                    onChange={(e) => setLangSearch(e.target.value)}
                  />
                </div>
                <div className="max-h-48 overflow-y-auto p-1">
                  {filteredLanguages.map((lang) => (
                    <button
                      key={lang.code}
                      type="button"
                      className={`w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-accent ${
                        data.preferredLanguage === lang.code
                          ? 'bg-accent font-medium'
                          : ''
                      }`}
                      onClick={() => {
                        onChange({ preferredLanguage: lang.code });
                        setLangOpen(false);
                        setLangSearch('');
                      }}
                    >
                      {lang.name}
                    </button>
                  ))}
                  {filteredLanguages.length === 0 && (
                    <p className="px-3 py-2 text-sm text-muted-foreground">No languages found</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack} className="flex-1">
          Back
        </Button>
        <Button onClick={onNext} disabled={!isValid} className="flex-1">
          Continue
        </Button>
      </div>
    </div>
  );
}
