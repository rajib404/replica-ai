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
import { api } from '@/lib/api';

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
            <div className="mt-4 space-y-4">
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
