import { LucideIcon } from 'lucide-react';

interface KPICardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  color: string;
}

const KPICard = ({ label, value, subtitle, icon: Icon, color }: KPICardProps) => {
  return (
    <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg flex items-center justify-between">
      <div className="space-y-2">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
          {label}
        </span>
        <span className="text-3xl font-extrabold text-white block">{value}</span>
        {subtitle && (
          <span className="text-xxs font-medium text-slate-500 block">{subtitle}</span>
        )}
      </div>
      <div
        className={`h-12 w-12 rounded-2xl flex items-center justify-center ${color}`}
      >
        <Icon size={22} />
      </div>
    </div>
  );
};

export default KPICard;
