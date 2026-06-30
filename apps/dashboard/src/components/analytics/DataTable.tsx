import { ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (item: T) => React.ReactNode;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  page: number;
  totalPages: number;
  total: number;
  limit: number;
  sort: string;
  order: string;
  onPageChange: (page: number) => void;
  onSortChange: (sort: string) => void;
  onOrderChange: (order: string) => void;
  onRowClick?: (item: T) => void;
}

function DataTable<T extends Record<string, any>>({
  data,
  columns,
  page,
  totalPages,
  total,
  limit,
  sort,
  order,
  onPageChange,
  onSortChange,
  onOrderChange,
  onRowClick,
}: DataTableProps<T>) {
  const handleSort = (key: string) => {
    if (sort === key) {
      onOrderChange(order === 'desc' ? 'asc' : 'desc');
    } else {
      onSortChange(key);
      onOrderChange('desc');
    }
  };

  const SortIcon = ({ columnKey }: { columnKey: string }) => {
    if (sort !== columnKey) return <ArrowUpDown size={12} className="text-slate-600" />;
    return order === 'desc' ? (
      <ArrowDown size={12} className="text-violet-400" />
    ) : (
      <ArrowUp size={12} className="text-violet-400" />
    );
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950 shadow-2xl">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800/60 text-slate-400 text-xs font-semibold uppercase tracking-wider bg-slate-900/30">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-6 py-4.5 ${col.sortable ? 'cursor-pointer hover:text-slate-200 select-none' : ''}`}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  <div className="flex items-center gap-1.5">
                    <span>{col.label}</span>
                    {col.sortable && <SortIcon columnKey={col.key} />}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-850 text-slate-300">
            {data.map((item, idx) => (
              <tr
                key={item.tenant_id || idx}
                className={`hover:bg-slate-900/10 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
                onClick={() => onRowClick?.(item)}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-6 py-4.5">
                    {col.render ? col.render(item) : item[col.key]}
                  </td>
                ))}
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-6 py-16 text-center text-slate-500 font-medium"
                >
                  No data available.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-900 bg-slate-950 px-6 py-4">
          <div className="text-xs text-slate-500 font-medium">
            Showing <span className="font-semibold text-slate-350">{(page - 1) * limit + 1}</span> to{' '}
            <span className="font-semibold text-slate-350">{Math.min(page * limit, total)}</span> of{' '}
            <span className="font-semibold text-slate-350">{total}</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page === 1}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-400 hover:bg-slate-900/60 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
            >
              <ChevronLeft size={16} />
            </button>

            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4));
              return start + i;
            })
              .filter((p) => p >= 1 && p <= totalPages)
              .map((p) => (
                <button
                  key={p}
                  onClick={() => onPageChange(p)}
                  className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                    p === page
                      ? 'bg-violet-600 text-white shadow-md shadow-violet-900/20'
                      : 'border border-transparent text-slate-400 hover:bg-slate-900/40 hover:text-slate-200'
                  }`}
                >
                  {p}
                </button>
              ))}

            <button
              onClick={() => onPageChange(Math.min(totalPages, page + 1))}
              disabled={page === totalPages}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-400 hover:bg-slate-900/60 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DataTable;
