import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { TimeSeriesPoint } from '../../interfaces';

interface TimeSeriesChartProps {
  data: TimeSeriesPoint[];
  dataKey: string;
  title: string;
  color: string;
  formatter?: (value: number) => string;
}

const TimeSeriesChart = ({
  data,
  dataKey,
  title,
  color,
  formatter,
}: TimeSeriesChartProps) => {
  const formatValue = formatter || ((v: number) => v.toLocaleString());

  return (
    <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
      <h3 className="text-sm font-bold text-white mb-4">{title}</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`gradient-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: string) => {
                const d = new Date(v);
                return d.toLocaleDateString('en-IN', {
                  month: 'numeric',
                  day: 'numeric',
                  timeZone: 'Asia/Kolkata',
                });
              }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => formatValue(v)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                color: '#e2e8f0',
                fontSize: '12px',
              }}
              labelFormatter={(label: string) => {
                const d = new Date(label);
                return d.toLocaleDateString('en-IN', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                  timeZone: 'Asia/Kolkata',
                });
              }}
              formatter={(value: number) => [formatValue(value), title]}
            />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={2}
              fill={`url(#gradient-${dataKey})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TimeSeriesChart;
