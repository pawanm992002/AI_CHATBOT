import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  MessageSquare,
  Coins,
  Target,
  ThumbsUp,
  TrendingUp,
  Layers,
  UserCheck,
  Clock,
  AlertTriangle,
  Cpu,
} from 'lucide-react';
import { PlatformOverview, TimeSeriesPoint, TenantUsage, ModelUsage } from '../interfaces';
import {
  fetchOverview,
  fetchTimeseries,
  fetchTopTenants,
  fetchModelLeaderboard,
} from '../services/adminAnalytics';
import { formatDate } from '../utils/date';
import KPICard from '../components/analytics/KPICard';
import TimeSeriesChart from '../components/analytics/TimeSeriesChart';
import FeedbackBreakdown from '../components/analytics/FeedbackBreakdown';
import DateRangeFilter from '../components/analytics/DateRangeFilter';
import ModelUsageTable from '../components/analytics/ModelUsageTable';
import TenantSelector from '../components/analytics/TenantSelector';
import { LoadingSpinner } from '@chatbot/shared';

const AdminAnalytics = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState('30d');
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [timeseries, setTimeseries] = useState<TimeSeriesPoint[]>([]);
  const [topTenants, setTopTenants] = useState<TenantUsage[]>([]);
  const [modelLeaderboard, setModelLeaderboard] = useState<ModelUsage[]>([]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const [overviewData, tsData, topData, modelData] = await Promise.all([
        fetchOverview(),
        fetchTimeseries(period),
        fetchTopTenants('messages', 10),
        fetchModelLeaderboard(period),
      ]);
      setOverview(overviewData);
      setTimeseries(tsData);
      setTopTenants(topData);
      setModelLeaderboard(modelData);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading && !overview) {
    return <LoadingSpinner message="Loading analytics..." />;
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-xl bg-rose-950/40 p-6 text-rose-400 border border-rose-900/60 max-w-2xl mx-auto mt-8">
        <div>
          <h3 className="font-bold text-white">Error</h3>
          <p className="text-sm mt-0.5">{error}</p>
          <button
            onClick={loadData}
            className="mt-3 text-xs font-bold text-violet-400 hover:text-violet-300 hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fadeIn text-slate-100">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Platform Analytics</h2>
          <p className="text-slate-400 text-sm mt-1">
            Cross-tenant usage metrics, token consumption, and engagement data.
          </p>
        </div>
        <DateRangeFilter value={period} onChange={setPeriod} />
      </div>

      {/* Jump to Tenant */}
      <TenantSelector className="max-w-md" />

      {overview && (
        <>
          {/* Top row: Tenants, Active, Messages, Tokens */}
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label="Total Tenants"
              value={overview.total_tenants}
              icon={Users}
              color="bg-violet-950/40 text-violet-400 border border-violet-900/40"
            />
            <KPICard
              label="Active Tenants"
              value={overview.active_tenants}
              subtitle="Last 30 days"
              icon={UserCheck}
              color="bg-teal-950/40 text-teal-400 border border-teal-900/40"
            />
            <KPICard
              label="Messages"
              value={overview.total_messages.toLocaleString()}
              subtitle={`${overview.total_conversations.toLocaleString()} conversations`}
              icon={MessageSquare}
              color="bg-blue-950/40 text-blue-400 border border-blue-900/40"
            />
            <KPICard
              label="Tokens"
              value={overview.total_tokens.toLocaleString()}
              subtitle={`${overview.prompt_tokens.toLocaleString()} prompt / ${overview.completion_tokens.toLocaleString()} completion`}
              icon={Layers}
              color="bg-indigo-950/40 text-indigo-400 border border-indigo-900/40"
            />
          </div>

          {/* Second row: Cost, Leads, Conversion, Like Ratio */}
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label="Estimated Cost"
              value={`$${overview.estimated_cost.toFixed(2)}`}
              subtitle="Based on token usage"
              icon={Coins}
              color="bg-amber-950/40 text-amber-400 border border-amber-900/40"
            />
            <KPICard
              label="Leads"
              value={overview.total_leads.toLocaleString()}
              icon={Target}
              color="bg-emerald-950/40 text-emerald-400 border border-emerald-900/40"
            />
            <KPICard
              label="Lead Conversion"
              value={`${overview.lead_conversion}%`}
              subtitle="Leads / Conversations"
              icon={TrendingUp}
              color="bg-cyan-950/40 text-cyan-400 border border-cyan-900/40"
            />
            <KPICard
              label="Like Ratio"
              value={`${overview.like_ratio}%`}
              subtitle={`${overview.like_count} likes / ${overview.dislike_count} dislikes`}
              icon={ThumbsUp}
              color="bg-rose-950/40 text-rose-400 border border-rose-900/40"
            />
          </div>

          {/* Third row: Latency, Errors */}
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label="Avg Latency"
              value={`${overview.avg_latency_ms.toFixed(0)}ms`}
              subtitle="Per LLM call"
              icon={Clock}
              color="bg-cyan-950/40 text-cyan-400 border border-cyan-900/40"
            />
            <KPICard
              label="Error Rate"
              value={`${overview.error_rate}%`}
              subtitle={`${overview.error_count} errors / ${overview.success_count} success`}
              icon={AlertTriangle}
              color="bg-rose-950/40 text-rose-400 border border-rose-900/40"
            />
          </div>

          {/* Charts */}
          <div className="grid gap-6 lg:grid-cols-2">
            <TimeSeriesChart
              data={timeseries}
              dataKey="messages"
              title="Daily Messages"
              color="#6366f1"
            />
            <TimeSeriesChart
              data={timeseries}
              dataKey="tokens"
              title="Daily Tokens"
              color="#8b5cf6"
              formatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toLocaleString()}
            />
            <TimeSeriesChart
              data={timeseries}
              dataKey="cost"
              title="Daily Cost"
              color="#f59e0b"
              formatter={(v: number) => `$${v.toFixed(4)}`}
            />
            <TimeSeriesChart
              data={timeseries}
              dataKey="leads"
              title="Daily Leads"
              color="#22c55e"
            />
          </div>

          {/* Model Usage */}
          <ModelUsageTable data={overview.model_usage} />

          {/* Model Leaderboard */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <div className="flex items-center gap-2 mb-4">
              <Cpu size={16} className="text-slate-400" />
              <h3 className="text-sm font-bold text-white">Model Leaderboard</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-800/60 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                    <th className="pb-3">#</th>
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
                  {modelLeaderboard.map((m, i) => (
                    <tr key={`${m.provider}-${m.model}-${i}`} className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 text-sm text-slate-500 font-mono">{i + 1}</td>
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
                  {modelLeaderboard.length === 0 && (
                    <tr>
                      <td colSpan={10} className="py-8 text-center text-slate-500 text-sm">
                        No model data yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Feedback + Top Tenants */}
          <div className="grid gap-6 lg:grid-cols-3">
            <FeedbackBreakdown
              likes={overview.like_count}
              dislikes={overview.dislike_count}
            />
            <div className="lg:col-span-2 bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
              <h3 className="text-sm font-bold text-white mb-4">Top Tenants</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-slate-800/60 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                      <th className="pb-3">Domain</th>
                      <th className="pb-3 text-right">Messages</th>
                      <th className="pb-3 text-right">Tokens</th>
                      <th className="pb-3 text-right">Cost</th>
                      <th className="pb-3 text-right">Leads</th>
                      <th className="pb-3 text-right">Last Active</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {topTenants.map((t) => (
                      <tr
                        key={t.tenant_id}
                        className="hover:bg-slate-800/20 cursor-pointer transition-colors"
                        onClick={() => navigate(`/admin/analytics/${t.tenant_id}`)}
                      >
                        <td className="py-3 text-sm text-white font-medium">{t.domain}</td>
                        <td className="py-3 text-sm text-slate-300 text-right">
                          {t.messages.toLocaleString()}
                        </td>
                        <td className="py-3 text-sm text-slate-300 text-right">
                          {t.total_tokens.toLocaleString()}
                        </td>
                        <td className="py-3 text-sm text-amber-400 text-right">
                          ${t.estimated_cost.toFixed(2)}
                        </td>
                        <td className="py-3 text-sm text-slate-300 text-right">{t.leads}</td>
                        <td className="py-3 text-xs text-slate-500 text-right">
                          {t.last_activity ? formatDate(t.last_activity) : '—'}
                        </td>
                      </tr>
                    ))}
                    {topTenants.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-slate-500 text-sm">
                          No tenant data yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AdminAnalytics;
