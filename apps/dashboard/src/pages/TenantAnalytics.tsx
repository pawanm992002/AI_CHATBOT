import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  MessageSquare,
  Coins,
  Target,
  ThumbsUp,
  TrendingUp,
  Layers,
  Users,
  Globe,
  Calendar,
} from 'lucide-react';
import { TenantAnalyticsDetail } from '../interfaces';
import { fetchTenantAnalytics } from '../services/adminAnalytics';
import { formatDate } from '../utils/date';
import KPICard from '../components/analytics/KPICard';
import TimeSeriesChart from '../components/analytics/TimeSeriesChart';
import FeedbackBreakdown from '../components/analytics/FeedbackBreakdown';
import DateRangeFilter from '../components/analytics/DateRangeFilter';
import ModelUsageTable from '../components/analytics/ModelUsageTable';
import TenantSelector from '../components/analytics/TenantSelector';
import { LoadingSpinner } from '@chatbot/shared';

const TenantAnalytics = () => {
  const { tenantId } = useParams<{ tenantId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState<TenantAnalyticsDetail | null>(null);

  const loadData = useCallback(async () => {
    if (!tenantId) return;
    try {
      setLoading(true);
      setError('');
      const result = await fetchTenantAnalytics(tenantId, period);
      setData(result);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load tenant analytics');
    } finally {
      setLoading(false);
    }
  }, [tenantId, period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading && !data) {
    return <LoadingSpinner message="Loading tenant analytics..." />;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/admin/analytics')}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors cursor-pointer"
        >
          <ArrowLeft size={16} />
          Back to Analytics
        </button>
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
      </div>
    );
  }

  if (!data) return null;

  const { tenant, kpi, timeseries } = data;

  return (
    <div className="space-y-8 animate-fadeIn text-slate-100">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div className="space-y-2">
          <button
            onClick={() => navigate('/admin/analytics')}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            <ArrowLeft size={16} />
            Back to Analytics
          </button>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-white">
              <Globe size={20} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white tracking-tight">
                {tenant.business_name || tenant.domain}
              </h2>
              <div className="flex items-center gap-3 text-sm text-slate-400">
                <span>{tenant.domain}</span>
                <span className="text-slate-600">|</span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${
                  tenant.plan === 'pro'
                    ? 'bg-purple-900/30 text-purple-400 border border-purple-800/40'
                    : 'bg-slate-800 text-slate-400 border border-slate-700/20'
                }`}>
                  {tenant.plan}
                </span>
                <span className="text-slate-600">|</span>
                <span className="flex items-center gap-1">
                  <Calendar size={12} />
                  Joined {formatDate(tenant.created_at)}
                </span>
              </div>
            </div>
          </div>
        </div>
        <DateRangeFilter value={period} onChange={setPeriod} />
        <TenantSelector className="w-64" placeholder="Switch tenant..." />
      </div>

      {/* KPIs Row 1 */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label="Conversations"
          value={kpi.conversations.toLocaleString()}
          icon={MessageSquare}
          color="bg-blue-950/40 text-blue-400 border border-blue-900/40"
        />
        <KPICard
          label="Visitors"
          value={kpi.visitors.toLocaleString()}
          icon={Users}
          color="bg-teal-950/40 text-teal-400 border border-teal-900/40"
        />
        <KPICard
          label="Messages"
          value={kpi.messages.toLocaleString()}
          icon={Layers}
          color="bg-indigo-950/40 text-indigo-400 border border-indigo-900/40"
        />
        <KPICard
          label="Tokens"
          value={kpi.total_tokens.toLocaleString()}
          subtitle={`${kpi.prompt_tokens.toLocaleString()} prompt / ${kpi.completion_tokens.toLocaleString()} completion`}
          icon={Layers}
          color="bg-violet-950/40 text-violet-400 border border-violet-900/40"
        />
      </div>

      {/* KPIs Row 2 */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label="Estimated Cost"
          value={`$${kpi.estimated_cost.toFixed(2)}`}
          icon={Coins}
          color="bg-amber-950/40 text-amber-400 border border-amber-900/40"
        />
        <KPICard
          label="Leads"
          value={kpi.leads.toLocaleString()}
          icon={Target}
          color="bg-emerald-950/40 text-emerald-400 border border-emerald-900/40"
        />
        <KPICard
          label="Lead Conversion"
          value={`${kpi.lead_conversion}%`}
          subtitle="Leads / Conversations"
          icon={TrendingUp}
          color="bg-cyan-950/40 text-cyan-400 border border-cyan-900/40"
        />
        <KPICard
          label="Like Ratio"
          value={`${kpi.like_ratio}%`}
          subtitle={`${kpi.likes} likes / ${kpi.dislikes} dislikes`}
          icon={ThumbsUp}
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
      </div>

      {/* Model Usage */}
      <ModelUsageTable data={kpi.model_usage} />

      {/* Feedback */}
      <FeedbackBreakdown likes={kpi.likes} dislikes={kpi.dislikes} />

      {/* Last Activity */}
      {kpi.last_activity && (
        <div className="text-xs text-slate-500">
          Last activity: {formatDate(kpi.last_activity)}
        </div>
      )}
    </div>
  );
};

export default TenantAnalytics;
