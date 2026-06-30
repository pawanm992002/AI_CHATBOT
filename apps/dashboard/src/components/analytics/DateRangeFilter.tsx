interface DateRangeFilterProps {
  value: string;
  onChange: (value: string) => void;
}

const PERIODS = [
  { label: '7D', value: '7d' },
  { label: '30D', value: '30d' },
  { label: '90D', value: '90d' },
  { label: '1Y', value: '1y' },
];

const DateRangeFilter = ({ value, onChange }: DateRangeFilterProps) => {
  return (
    <div className="flex gap-1 bg-slate-900 rounded-xl border border-slate-800/80 p-1">
      {PERIODS.map((period) => (
        <button
          key={period.value}
          onClick={() => onChange(period.value)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
            value === period.value
              ? 'bg-violet-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          {period.label}
        </button>
      ))}
    </div>
  );
};

export default DateRangeFilter;
