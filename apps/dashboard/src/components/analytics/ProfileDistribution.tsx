import { Tag } from 'lucide-react';

interface ProfileDistributionItem {
  profile_id: string | null;
  label: string | null;
  count: number;
  percentage: number;
}

interface ProfileDistributionProps {
  data: ProfileDistributionItem[];
}

function ProfileDistribution({ data }: ProfileDistributionProps) {
  if (data.length === 0) {
    return (
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
        <div className="flex items-center gap-2 mb-4">
          <Tag size={16} className="text-slate-400" />
          <h3 className="text-sm font-bold text-white">Profile Distribution</h3>
        </div>
        <p className="text-sm text-slate-500 text-center py-6">No visitor profile data yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
      <div className="flex items-center gap-2 mb-4">
        <Tag size={16} className="text-slate-400" />
        <h3 className="text-sm font-bold text-white">Profile Distribution</h3>
      </div>
      <div className="space-y-3">
        {data.map((item, i) => (
          <div key={item.profile_id || 'unclassified'} className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm font-medium text-slate-200 truncate">
                  {item.label || 'Unclassified'}
                </span>
                <span className="text-xs text-slate-400 ml-2">
                  {item.count.toLocaleString()} ({item.percentage.toFixed(1)}%)
                </span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${item.percentage}%`,
                    backgroundColor: item.profile_id ? undefined : '#475569',
                  }}
                >
                  {item.profile_id && (
                    <div
                      className="h-full rounded-full"
                      style={{ backgroundColor: `hsl(${i * 60}, 70%, 50%)` }}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ProfileDistribution;