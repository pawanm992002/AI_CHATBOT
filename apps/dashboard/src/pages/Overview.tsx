import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { useStore } from '../store';
import { 
  Database, 
  Layers, 
  HelpCircle, 
  MessageSquare, 
  TrendingUp,
  CheckCircle,
  Chrome,
  Monitor,
  ExternalLink
} from 'lucide-react';

interface TenantStatsData {
  pages_crawled: number;
  chunks_indexed: number;
  queries_this_month: number;
  knowledge_sources: number;
}

const Overview = () => {
  const { state, dispatch } = useStore();
  const [tenantStats, setTenantStats] = useState<TenantStatsData | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        dispatch({ type: 'SET_LOADING', payload: true });
        const [statsRes, gapsRes] = await Promise.all([
          privateAxios.get('/tenants/stats'),
          privateAxios.get('/dashboard/knowledge/gaps/stats'),
        ]);

        if (statsRes.status === 200) {
          setTenantStats(statsRes.data);
          dispatch({ type: 'SET_SOURCES', payload: statsRes.data.knowledge_sources || 0 });
        }
        if (gapsRes.status === 200) {
          dispatch({ type: 'SET_STATS', payload: gapsRes.data });
        }
      } catch (err: any) {
        dispatch({ type: 'SET_ERROR', payload: err.message || 'Failed to load dashboard data' });
      } finally {
        dispatch({ type: 'SET_LOADING', payload: false });
      }
    };
    fetchData();
  }, [dispatch]);

  const gapStats = state.stats;

  // Dark Theme KPIs
  const kpis = [
    { 
      label: 'Knowledge Sources', 
      val: tenantStats?.knowledge_sources ?? '-', 
      sub: 'Websites, PDFs, FAQs, Docs', 
      icon: Database,
      color: 'bg-violet-950/40 text-violet-400 border border-violet-900/40'
    },
    { 
      label: 'Pages Crawled', 
      val: tenantStats?.pages_crawled ?? '-', 
      sub: 'Across all websites', 
      icon: Chrome,
      color: 'bg-blue-950/40 text-blue-400 border border-blue-900/40'
    },
    { 
      label: 'Chunks Indexed', 
      val: tenantStats?.chunks_indexed ?? '-', 
      sub: 'Searchable vectors', 
      icon: Layers,
      color: 'bg-indigo-950/40 text-indigo-400 border border-indigo-900/40'
    },
    { 
      label: 'Queries This Month', 
      val: tenantStats?.queries_this_month ?? '-', 
      sub: 'Total chat sessions', 
      icon: MessageSquare,
      color: 'bg-teal-950/40 text-teal-400 border border-teal-900/40'
    },
  ];

  return (
    <div className="space-y-8 animate-fadeIn text-slate-100">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Console Overview</h2>
          <p className="text-slate-400 text-sm mt-1">Real-time status of chatbot responses, vector search health, and user queries.</p>
        </div>
        <div className="flex items-center gap-3 mt-4 sm:mt-0">
          <a
            href="/tenants/test"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 text-sm font-semibold text-white rounded-xl shadow-sm hover:bg-teal-700 transition-colors"
          >
            <Monitor size={16} />
            <span>Test Chatbot</span>
          </a>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi, idx) => {
          const Icon = kpi.icon;
          return (
            <div key={idx} className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg flex items-center justify-between">
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">{kpi.label}</span>
                <span className="text-3xl font-extrabold text-white block">{kpi.val}</span>
                <span className="text-xxs font-medium text-slate-500 block">{kpi.sub}</span>
              </div>
              <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${kpi.color}`}>
                <Icon size={22} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Stats Cards Section */}
      {gapStats && (
        <div className="grid gap-6 md:grid-cols-3">
          {/* Health Card */}
          <div className="md:col-span-2 bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <h3 className="text-md font-bold text-white mb-6 flex items-center gap-2">
              <TrendingUp size={18} className="text-violet-400" />
              <span>Knowledge Health Status</span>
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-rose-950/30 rounded-2xl p-4 border border-rose-900/40 text-center">
                <span className="text-2xl font-extrabold text-rose-400 block">{gapStats.open}</span>
                <span className="text-xs font-semibold text-slate-400 mt-1 block">Unresolved Gaps</span>
              </div>
              <div className="bg-teal-950/30 rounded-2xl p-4 border border-teal-900/40 text-center">
                <span className="text-2xl font-extrabold text-teal-400 block">{gapStats.resolved}</span>
                <span className="text-xs font-semibold text-slate-400 mt-1 block">Resolved FAQs</span>
              </div>
              <div className="bg-slate-950 rounded-2xl p-4 border border-slate-800 text-center">
                <span className="text-2xl font-extrabold text-slate-300 block">{gapStats.total}</span>
                <span className="text-xs font-semibold text-slate-400 mt-1 block">Total Gaps</span>
              </div>
            </div>
          </div>

          {/* Top Unanswered Questions */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <h3 className="text-md font-bold text-white mb-6 flex items-center gap-2">
              <HelpCircle size={18} className="text-amber-400" />
              <span>Top Unresolved Queries</span>
            </h3>
            <div className="space-y-4">
              {gapStats.top_gaps?.slice(0, 3).map((g, idx) => (
                <div key={g.gap_id || idx} className="flex items-center justify-between gap-3 bg-slate-950 p-3 rounded-xl border border-slate-800/50">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-xs font-bold text-slate-500">#{idx + 1}</span>
                    <span className="text-xs font-semibold text-slate-300 truncate" title={g.query}>{g.query}</span>
                  </div>
                  <span className="flex-shrink-0 inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xxs font-bold bg-amber-950/80 text-amber-300 border border-amber-900/50">
                    {g.count}x
                  </span>
                </div>
              ))}
              {(!gapStats.top_gaps || gapStats.top_gaps.length === 0) && (
                <div className="flex flex-col items-center justify-center py-6 text-slate-500">
                  <CheckCircle size={24} className="text-teal-400 mb-2" />
                  <span className="text-xs font-medium">All clear! No unanswered queries.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Overview;