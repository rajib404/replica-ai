'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from 'recharts';
import type { StorageProjectionPoint } from '@/lib/admin/types';

export default function StorageProjectionChart({ data }: { data: StorageProjectionPoint[] }) {
  // Split historical and projected so we can render two lines
  const merged = data.map((d) => ({
    date: d.date,
    historical: d.projected ? null : d.value,
    projected: d.projected ? d.value : null,
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <LineChart data={merged} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line
          type="monotone"
          dataKey="historical"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          dot={false}
          name="Historical"
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="projected"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
          name="Projected"
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
