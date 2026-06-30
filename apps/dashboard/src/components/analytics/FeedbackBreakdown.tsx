import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

interface FeedbackBreakdownProps {
  likes: number;
  dislikes: number;
}

const COLORS = ['#22c55e', '#ef4444'];

const FeedbackBreakdown = ({ likes, dislikes }: FeedbackBreakdownProps) => {
  const total = likes + dislikes;
  const data = [
    { name: 'Likes', value: likes },
    { name: 'Dislikes', value: dislikes },
  ];

  if (total === 0) {
    return (
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
        <h3 className="text-sm font-bold text-white mb-4">Feedback</h3>
        <div className="flex items-center justify-center h-40 text-slate-500 text-xs">
          No feedback yet
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
      <h3 className="text-sm font-bold text-white mb-4">Feedback</h3>
      <div className="flex items-center gap-6">
        <div className="w-32 h-32">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={30}
                outerRadius={50}
                paddingAngle={4}
                dataKey="value"
              >
                {data.map((_entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '12px',
                  color: '#e2e8f0',
                  fontSize: '12px',
                }}
                formatter={(value: number) => [value, '']}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-green-500" />
            <span className="text-xs text-slate-400">Likes</span>
            <span className="text-sm font-bold text-white ml-auto">{likes}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-red-500" />
            <span className="text-xs text-slate-400">Dislikes</span>
            <span className="text-sm font-bold text-white ml-auto">{dislikes}</span>
          </div>
          <div className="pt-2 border-t border-slate-800">
            <span className="text-xs text-slate-400">Like Ratio</span>
            <span className="text-sm font-bold text-white ml-2">
              {total > 0 ? ((likes / total) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FeedbackBreakdown;
