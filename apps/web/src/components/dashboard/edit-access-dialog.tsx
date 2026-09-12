'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { AccessRule } from '@replica-ai/shared';
import { api } from '@/lib/api';
import {
  CONTENT_TYPES,
  INFORMATION_CATEGORIES,
  ALL_CONTENT_TYPES,
  ALL_INFORMATION_CATEGORIES,
  CategoryCheckboxGroup,
  toAllowedList,
} from './create-rule-dialog';

const ACCESS_LEVELS = [
  { value: 'full', label: 'Full Access' },
  { value: 'read_only', label: 'Read Only' },
  { value: 'limited', label: 'Limited' },
] as const;

function toSet(values: string[] | null, all: Set<string>): Set<string> {
  return values === null ? new Set(all) : new Set(values);
}

function parseCsv(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

interface EditAccessDialogProps {
  rule: AccessRule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

export function EditAccessDialog({ rule, open, onOpenChange, onSaved }: EditAccessDialogProps) {
  const [accessLevel, setAccessLevel] = useState(rule.accessLevel);
  const [allowedTopics, setAllowedTopics] = useState(
    rule.topicRestrictions?.allowed.join(', ') ?? ''
  );
  const [blockedTopics, setBlockedTopics] = useState(
    rule.topicRestrictions?.blocked.join(', ') ?? ''
  );
  const [allowedContentTypes, setAllowedContentTypes] = useState(
    toSet(rule.allowedContentTypes, ALL_CONTENT_TYPES)
  );
  const [allowedCategories, setAllowedCategories] = useState(
    toSet(rule.allowedInformationCategories, ALL_INFORMATION_CATEGORIES)
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const allowed = parseCsv(allowedTopics);
      const blocked = parseCsv(blockedTopics);
      await api.put(`/api/access/rules/${rule.id}`, {
        access_level: accessLevel,
        topic_restrictions: allowed.length || blocked.length ? { allowed, blocked } : null,
        allowed_content_types: toAllowedList(allowedContentTypes, ALL_CONTENT_TYPES),
        allowed_information_categories: toAllowedList(allowedCategories, ALL_INFORMATION_CATEGORIES),
      });
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to update rule');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit access for {rule.granteeName}</DialogTitle>
            <DialogDescription>
              Control exactly what {rule.granteeName} can see and discuss.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 max-h-[60vh] space-y-4 overflow-y-auto pr-1">
            <div className="space-y-2">
              <Label>Access Level</Label>
              <div className="flex gap-2">
                {ACCESS_LEVELS.map((al) => (
                  <button
                    key={al.value}
                    type="button"
                    onClick={() => setAccessLevel(al.value)}
                    className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                      accessLevel === al.value
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-input bg-background hover:bg-accent'
                    }`}
                  >
                    {al.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {accessLevel === 'full'
                  ? 'Full access shares everything below — narrow it down by switching to Read Only or Limited.'
                  : 'Uncheck anything this person should not see. Leave everything checked for no restriction.'}
              </p>
            </div>

            <CategoryCheckboxGroup
              title="Content types"
              options={CONTENT_TYPES}
              selected={accessLevel === 'full' ? ALL_CONTENT_TYPES : allowedContentTypes}
              onChange={setAllowedContentTypes}
              disabled={accessLevel === 'full'}
            />

            <CategoryCheckboxGroup
              title="Information categories"
              options={INFORMATION_CATEGORIES}
              selected={accessLevel === 'full' ? ALL_INFORMATION_CATEGORIES : allowedCategories}
              onChange={setAllowedCategories}
              disabled={accessLevel === 'full'}
            />

            <div className="space-y-2">
              <Label htmlFor="allowed-topics">Allowed topics (comma-separated, optional)</Label>
              <Textarea
                id="allowed-topics"
                value={allowedTopics}
                onChange={(e) => setAllowedTopics(e.target.value)}
                placeholder="e.g. family stories, recipes, travel"
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="blocked-topics">Blocked topics (comma-separated, optional)</Label>
              <Textarea
                id="blocked-topics"
                value={blockedTopics}
                onChange={(e) => setBlockedTopics(e.target.value)}
                placeholder="e.g. finances, medical, passwords"
                rows={2}
              />
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving...' : 'Save changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
