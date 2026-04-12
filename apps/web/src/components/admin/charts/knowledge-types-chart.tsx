'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import type { KnowledgeTypeBucket } from '@/lib/admin/types';

const COLORS = [
  'hsl(var(--primary))',
  'hsl(173 58% 39%)',
  'hsl(43 74% 66%)',
  'hsl(27 87% 67%)',
  'hsl(12 76% 61%)',
  'hsl(197 37% 24%)',
];

export default function KnowledgeTypesChart({ data }: { data: KnowledgeTypeBucket[] }) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="content_type"
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={90}
          paddingAngle={2}
        >
          {data.map((_, idx) => (
            <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
