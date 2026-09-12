import { Settings } from 'lucide-react';
import { AccountSection } from '@/components/settings/account-section';
import { EnrollmentSection } from '@/components/settings/enrollment-section';

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8 p-8">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <Settings className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Configure your Replica&apos;s behavior and security settings.
          </p>
        </div>
      </div>

      <AccountSection />
      <EnrollmentSection />
    </div>
  );
}
