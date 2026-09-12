'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { api } from '@/lib/api';

export const CONTENT_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'audio', label: 'Audio' },
  { value: 'image', label: 'Photos' },
  { value: 'video', label: 'Video' },
  { value: 'document', label: 'Documents' },
] as const;

export const INFORMATION_CATEGORIES = [
  { value: 'memories_stories', label: 'Memories & Stories' },
  { value: 'photos_videos', label: 'Photos & Videos' },
  { value: 'voice_recordings', label: 'Voice Recordings' },
  { value: 'health_medical', label: 'Health & Medical' },
  { value: 'financial', label: 'Financial' },
  { value: 'legal_official', label: 'Legal & Official' },
  { value: 'relationships_family', label: 'Relationships & Family' },
  { value: 'career_work', label: 'Career & Work' },
  { value: 'beliefs_values', label: 'Beliefs & Values' },
  { value: 'traditions_recipes', label: 'Traditions & Recipes' },
  { value: 'advice_wisdom', label: 'Advice & Wisdom' },
  { value: 'general', label: 'General' },
] as const;

export function CategoryCheckboxGroup({
  title,
  options,
  selected,
  onChange,
  disabled,
}: {
  title: string;
  options: readonly { value: string; label: string }[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  disabled?: boolean;
}) {
  function toggle(value: string) {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(next);
  }

  return (
    <div className="space-y-2">
      <Label>{title}</Label>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-md border p-3 sm:grid-cols-3">
        {options.map((opt) => (
          <label
            key={opt.value}
            className="flex items-center gap-2 text-xs font-medium leading-none"
          >
            <Checkbox
              checked={selected.has(opt.value)}
              onCheckedChange={() => toggle(opt.value)}
              disabled={disabled}
            />
            {opt.label}
          </label>
        ))}
      </div>
    </div>
  );
}

export const ALL_CONTENT_TYPES = new Set(CONTENT_TYPES.map((c) => c.value));
export const ALL_INFORMATION_CATEGORIES = new Set(INFORMATION_CATEGORIES.map((c) => c.value));

/** `null` (unrestricted) when everything is selected — only send an explicit
 * list once the owner has actually narrowed it down. */
export function toAllowedList(
  selected: Set<string>,
  all: Set<string>,
): string[] | null {
  return selected.size >= all.size ? null : Array.from(selected);
}

const RELATIONS = [
  { value: 'spouse', label: 'Spouse' },
  { value: 'son', label: 'Son' },
  { value: 'daughter', label: 'Daughter' },
  { value: 'grandson', label: 'Grandson' },
  { value: 'granddaughter', label: 'Granddaughter' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'parent', label: 'Parent' },
  { value: 'grandparent', label: 'Grandparent' },
  { value: 'friend', label: 'Friend' },
] as const;

const ACCESS_LEVELS = [
  { value: 'full', label: 'Full Access' },
  { value: 'read_only', label: 'Read Only' },
  { value: 'limited', label: 'Limited' },
] as const;

const VERIFICATION_METHODS = [
  { value: 'none', label: 'None' },
  { value: 'secret_word', label: 'Secret Word' },
  { value: 'secret_event', label: 'Secret Event' },
  { value: 'voice_match', label: 'Voice Match' },
] as const;

interface Template {
  name: string;
  label: string;
  description: string;
  config: {
    grantee_name: string;
    grantee_relation: string | null;
    access_level: string;
    verification_method: string;
    topic_restrictions: { allowed: string[]; blocked: string[] } | null;
    template_name: string | null;
  };
}

interface CreateRuleDialogProps {
  templates: Template[];
  onCreated: () => void;
}

export function CreateRuleDialog({ templates, onCreated }: CreateRuleDialogProps) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<'choose' | 'form'>('choose');

  // Form state
  const [granteeName, setGranteeName] = useState('');
  const [relation, setRelation] = useState('');
  const [accessLevel, setAccessLevel] = useState('limited');
  const [verificationMethod, setVerificationMethod] = useState('none');
  const [verificationValue, setVerificationValue] = useState('');
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [allowedContentTypes, setAllowedContentTypes] = useState<Set<string>>(new Set(ALL_CONTENT_TYPES));
  const [allowedCategories, setAllowedCategories] = useState<Set<string>>(new Set(ALL_INFORMATION_CATEGORIES));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  function applyTemplate(t: Template) {
    setRelation(t.config.grantee_relation ?? '');
    setAccessLevel(t.config.access_level);
    setVerificationMethod(t.config.verification_method);
    setTemplateName(t.config.template_name ?? t.name);
    setStep('form');
  }

  function resetForm() {
    setGranteeName('');
    setRelation('');
    setAccessLevel('limited');
    setVerificationMethod('none');
    setVerificationValue('');
    setTemplateName(null);
    setAllowedContentTypes(new Set(ALL_CONTENT_TYPES));
    setAllowedCategories(new Set(ALL_INFORMATION_CATEGORIES));
    setStep('choose');
    setError('');
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) resetForm();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      await api.post('/api/access/rules', {
        grantee_name: granteeName,
        grantee_relation: relation || null,
        access_level: accessLevel,
        verification_method: verificationMethod,
        verification_value: verificationValue || null,
        allowed_content_types: toAllowedList(allowedContentTypes, ALL_CONTENT_TYPES),
        allowed_information_categories: toAllowedList(allowedCategories, ALL_INFORMATION_CATEGORIES),
        template_name: templateName,
      });
      onCreated();
      handleOpenChange(false);
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to create rule');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>Add Access Rule</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        {step === 'choose' ? (
          <>
            <DialogHeader>
              <DialogTitle>Create Access Rule</DialogTitle>
              <DialogDescription>
                Pick a template or start from scratch.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4 grid gap-2">
              {templates.map((t) => (
                <button
                  key={t.name}
                  type="button"
                  onClick={() => applyTemplate(t)}
                  className="flex flex-col items-start rounded-md border px-4 py-3 text-left transition-colors hover:bg-accent"
                >
                  <span className="text-sm font-medium">{t.label}</span>
                  <span className="text-xs text-muted-foreground">{t.description}</span>
                </button>
              ))}
              <button
                type="button"
                onClick={() => setStep('form')}
                className="flex flex-col items-start rounded-md border border-dashed px-4 py-3 text-left transition-colors hover:bg-accent"
              >
                <span className="text-sm font-medium">Custom Rule</span>
                <span className="text-xs text-muted-foreground">Configure everything manually.</span>
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <DialogHeader>
              <DialogTitle>
                {templateName ? `Template: ${templateName.replace('_', ' ')}` : 'Custom Rule'}
              </DialogTitle>
              <DialogDescription>Set the details for this access rule.</DialogDescription>
            </DialogHeader>
            <div className="mt-4 max-h-[60vh] space-y-4 overflow-y-auto pr-1">
              <div className="space-y-2">
                <Label htmlFor="grantee-name">Name</Label>
                <Input
                  id="grantee-name"
                  value={granteeName}
                  onChange={(e) => setGranteeName(e.target.value)}
                  placeholder="e.g. Maria"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label>Relation</Label>
                <div className="flex flex-wrap gap-2">
                  {RELATIONS.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setRelation(r.value)}
                      className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                        relation === r.value
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background hover:bg-accent'
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

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
              </div>

              <div className="space-y-2">
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
                <Label>Verification</Label>
                <div className="flex flex-wrap gap-2">
                  {VERIFICATION_METHODS.map((vm) => (
                    <button
                      key={vm.value}
                      type="button"
                      onClick={() => setVerificationMethod(vm.value)}
                      className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                        verificationMethod === vm.value
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background hover:bg-accent'
                      }`}
                    >
                      {vm.label}
                    </button>
                  ))}
                </div>
              </div>

              {(verificationMethod === 'secret_word' || verificationMethod === 'secret_event') && (
                <div className="space-y-2">
                  <Label htmlFor="verification-value">
                    {verificationMethod === 'secret_word' ? 'Secret Word' : 'Secret Event'}
                  </Label>
                  <Input
                    id="verification-value"
                    type="password"
                    value={verificationValue}
                    onChange={(e) => setVerificationValue(e.target.value)}
                    placeholder={
                      verificationMethod === 'secret_word'
                        ? 'Enter a secret word...'
                        : 'Describe a shared event...'
                    }
                  />
                </div>
              )}

              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
            <DialogFooter className="mt-6">
              <Button type="button" variant="outline" onClick={() => setStep('choose')}>
                Back
              </Button>
              <Button type="submit" disabled={submitting || !granteeName}>
                {submitting ? 'Creating...' : 'Create Rule'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
