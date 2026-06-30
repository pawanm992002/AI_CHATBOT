import { Cpu } from 'lucide-react';
import { ModelUsage } from '../../interfaces';

interface ModelUsageTableProps {
  data: ModelUsage[];
}

function ModelUsageTable({ data }: ModelUsageTableProps) {
  if (data.length === 0) {
    return (
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
        <div className="flex items-center gap-2 mb-4">
          <Cpu size={16} className="text-slate-400" />
          <h3 className="text-sm font-bold text-white">Model Usage</h3>
        </div>
        <p className="text-sm text-slate-500 text-center py-6">No model usage data yet.</p>
      </div>
    );
  }

  const totalPrompt = data.reduce((s, m) => s + m.prompt_tokens, 0);
  const totalCompletion = data.reduce((s, m) => s + m.completion_tokens, 0);
  const totalCost = data.reduce((s, m) => s + m.cost, 0);

  return (
    <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
      <div className="flex items-center gap-2 mb-4">
        <Cpu size={16} className="text-slate-400" />
        <h3 className="text-sm font-bold text-white">Model Usage</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-800/60 text-slate-400 text-xs font-semibold uppercase tracking-wider">
              <th className="pb-3">Provider</th>
              <th className="pb-3">Model</th>
              <th className="pb-3 text-right">Calls</th>
              <th className="pb-3 text-right">Prompt</th>
              <th className="pb-3 text-right">Completion</th>
              <th className="pb-3 text-right">Total</th>
              <th className="pb-3 text-right">Avg Latency</th>
              <th className="pb-3 text-right">Errors</th>
              <th className="pb-3 text-right">Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/40">
            {data.map((m, i) => (
              <tr key={`${m.provider}-${m.model}-${i}`} className="hover:bg-slate-800/20 transition-colors">
                <td className="py-3 text-sm">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${
                    m.provider === 'openai'
                      ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/40'
                      : m.provider === 'groq'
                      ? 'bg-orange-900/30 text-orange-400 border border-orange-800/40'
                      : 'bg-blue-900/30 text-blue-400 border border-blue-800/40'
                  }`}>
                    {m.provider}
                  </span>
                </td>
                <td className="py-3 text-sm text-white font-medium">{m.model}</td>
                <td className="py-3 text-sm text-slate-300 text-right">{m.call_count.toLocaleString()}</td>
                <td className="py-3 text-sm text-slate-300 text-right">{m.prompt_tokens.toLocaleString()}</td>
                <td className="py-3 text-sm text-slate-300 text-right">{m.completion_tokens.toLocaleString()}</td>
                <td className="py-3 text-sm text-slate-300 text-right">{m.total_tokens.toLocaleString()}</td>
                <td className="py-3 text-sm text-cyan-400 text-right">{m.avg_latency_ms.toFixed(0)}ms</td>
                <td className="py-3 text-sm text-right">
                  {m.error_count > 0 ? (
                    <span className="text-rose-400">{m.error_count}</span>
                  ) : (
                    <span className="text-slate-600">0</span>
                  )}
                </td>
                <td className="py-3 text-sm text-amber-400 text-right">${m.cost.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-slate-800/60 text-slate-300 text-sm font-semibold">
              <td className="pt-3" colSpan={2}>Total</td>
              <td className="pt-3 text-right">{data.reduce((s, m) => s + m.call_count, 0).toLocaleString()}</td>
              <td className="pt-3 text-right">{totalPrompt.toLocaleString()}</td>
              <td className="pt-3 text-right">{totalCompletion.toLocaleString()}</td>
              <td className="pt-3 text-right">{(totalPrompt + totalCompletion).toLocaleString()}</td>
              <td className="pt-3 text-right text-cyan-400">
                {data.reduce((s, m) => s + m.call_count, 0) > 0
                  ? `${(data.reduce((s, m) => s + m.avg_latency_ms * m.call_count, 0) / data.reduce((s, m) => s + m.call_count, 0)).toFixed(0)}ms`
                  : '—'}
              </td>
              <td className="pt-3 text-right">{data.reduce((s, m) => s + m.error_count, 0)}</td>
              <td className="pt-3 text-right text-amber-400">${totalCost.toFixed(4)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export default ModelUsageTable;
