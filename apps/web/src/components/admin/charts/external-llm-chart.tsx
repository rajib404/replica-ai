'use client';

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from 'recharts';
import type { ExternalLLMUsagePoint } from '@/lib/admin/types';

const COLORS = [
  'hsl(var(--primary))',
  'hsl(173 58% 39%)',
  'hsl(43 74% 66%)',
  'hsl(27 87% 67%)',
];

export default function ExternalLLMChart({ data }: { data: ExternalLLMUsagePoint[] }) {
  // Pivot: rows by date, columns per provider
  const dateMap: Record<string, Record<string, number>> = {};
  const providers = new Set<string>();
  for (const row of data) {
    if (!dateMap[row.date]) dateMap[row.date] = {};
    dateMap[row.date][row.provider] = row.cost_usd;
    providers.add(row.provider);
  }
  const pivoted = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, byProvider]) => ({ date, ...byProvider }));
  const providerList = Array.from(providers);

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={pivoted} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v.toFixed(2)}`} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 6,
            fontSize: 12,
          }}
          formatter={(v: number) => `$${v.toFixed(4)}`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {providerList.map((provider, idx) => (
          <Bar
            key={provider}
            dataKey={provider}
            stackId="cost"
            fill={COLORS[idx % COLORS.length]}
            radius={idx === providerList.length - 1 ? [4, 4, 0, 0] : 0}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
