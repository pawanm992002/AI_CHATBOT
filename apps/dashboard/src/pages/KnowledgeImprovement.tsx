import { useEffect, useState, useCallback } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { useStore, hasAccess } from '../store';
import { KnowledgeGap, Source } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import { useRbacError } from '../hooks/useRbacError';
import { 
  Sparkles, 
  TrendingUp,
  X,
  Lock,
  Link as LinkIcon,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-amber-950/30 text-amber-400 border border-amber-900/30',
  resolved: 'bg-teal-950/30 text-teal-400 border border-teal-900/30',
  dismissed: 'bg-slate-950 text-slate-500 border border-slate-800',
};

const KnowledgeImprovement = () => {
  const { state, dispatch } = useStore();
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('open');
  const [gapType, setGapType] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [resolving, setResolving] = useState<string | null>(null);
  const [faqForm, setFaqForm] = useState({ question: '', answer: '', source_id: '' });
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const { rbacError, triggerRbacError } = useRbacError();

  const isEditor = hasAccess(state.role, 'write');

  const fetchGaps = useCallback(async () => {
    try {
      const skip = (page - 1) * pageSize;
      let url = `/dashboard/knowledge/gaps?status=${filter}&limit=${pageSize}&skip=${skip}`;
      if (gapType) url += `&gap_type=${gapType}`;
      
      const [gapsRes, statsRes, sourcesRes] = await Promise.all([
        privateAxios.get(url),
        privateAxios.get('/dashboard/knowledge/gaps/stats'),
        privateAxios.get('/dashboard/sources'),
      ]);

      setGaps(gapsRes.data.items);
      setTotal(gapsRes.data.total);
      setTotalPages(gapsRes.data.total_pages);
      dispatch({ type: 'SET_STATS', payload: statsRes.data });
      setSources(sourcesRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filter, gapType, page, dispatch]);

  useEffect(() => {
    setPage(1);
  }, [filter, gapType, pageSize]);

  useEffect(() => {
    fetchGaps();
  }, [fetchGaps]);

  const resolveGap = async (gapId: string, action: string, mergeIntoId?: string) => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to resolve or dismiss knowledge gaps.");
      return;
    }
    const body: Record<string, any> = { action };

    if (action === 'create_faq') {
      if (!faqForm.question.trim() || !faqForm.answer.trim() || !faqForm.source_id) return;
      body.faq_question = faqForm.question;
      body.faq_answer = faqForm.answer;
      body.source_id = faqForm.source_id;
    }

    if (action === 'merge') {
      if (!mergeIntoId) return;
      body.merge_into_id = mergeIntoId;
    }

    setResolving(gapId);
    try {
      await privateAxios.post(`/dashboard/knowledge/gaps/${gapId}/resolve`, body);
      setFaqForm({ question: '', answer: '', source_id: '' });
      setResolving(null);
      fetchGaps();
    } catch (err) {
      console.error(err);
      setResolving(null);
    }
  };

  const cleanupDuplicates = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to cleanup knowledge gaps.");
      return;
    }
    try {
      const res = await privateAxios.post('/dashboard/knowledge/gaps/cleanup');
      alert(`Merged ${res.data.merged} duplicate gaps. ${res.data.remaining} gaps remaining.`);
      fetchGaps();
    } catch (err) {
      console.error(err);
    }
  };

  const startResolve = (gap: any) => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to resolve knowledge gaps.");
      return;
    }
    setFaqForm((prev) => ({ ...prev, question: gap.query }));
    setResolving(gap.gap_id);
  };

  const cancelResolve = () => {
    setResolving(null);
    setFaqForm({ question: '', answer: '', source_id: '' });
  };

  if (loading) {
    return <LoadingSpinner message="Loading knowledge gaps..." />;
  }

  const stats = state.stats;

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header & Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Knowledge Gaps</h2>
          <p className="text-slate-400 text-sm mt-1">
            Questions requested by customers that your chatbot could not answer.
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-col gap-2 self-start sm:self-auto">
          <div className="flex items-center bg-slate-900 rounded-xl border border-slate-800 p-1 shadow-md">
            {['open', 'resolved', 'all'].map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-4 py-2 rounded-lg text-xs font-semibold capitalize transition-all cursor-pointer ${
                  filter === s 
                    ? 'bg-violet-600 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {s === 'open' ? 'Unresolved' : s}
              </button>
            ))}
            {filter === 'open' && isEditor && (
              <button
                onClick={cleanupDuplicates}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-amber-400 hover:bg-amber-950/30 transition-all cursor-pointer ml-2"
              >
                Cleanup Duplicates
              </button>
            )}
          </div>
          
          {filter === 'open' && (
            <div className="flex items-center bg-slate-900 rounded-xl border border-slate-800 p-1 shadow-md">
              <button
                onClick={() => setGapType(null)}
                className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  gapType === null 
                    ? 'bg-slate-700 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                All Types
              </button>
              <button
                onClick={() => setGapType('no_context')}
                className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  gapType === 'no_context' 
                    ? 'bg-rose-600 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                Knowledge Gaps
              </button>
              <button
                onClick={() => setGapType('out_of_scope')}
                className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  gapType === 'out_of_scope' 
                    ? 'bg-amber-600 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                Out of Scope
              </button>
            </div>
          )}
        </div>
      </div>

      {/* RBAC Error Banner */}
      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/20 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-6 sm:grid-cols-4">
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">Knowledge Gaps</span>
            <span className="text-3xl font-extrabold text-rose-400 mt-2 block">{stats.no_context || 0}</span>
            <span className="text-xxs text-slate-500">No relevant context found</span>
          </div>
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">Out of Scope</span>
            <span className="text-3xl font-extrabold text-amber-400 mt-2 block">{stats.out_of_scope || 0}</span>
            <span className="text-xxs text-slate-500">Unrelated to business</span>
          </div>
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">Resolved via FAQ</span>
            <span className="text-3xl font-extrabold text-teal-400 mt-2 block">{stats.resolved}</span>
          </div>
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">Total Recorded</span>
            <span className="text-3xl font-extrabold text-slate-300 mt-2 block">{stats.total}</span>
          </div>
        </div>
      )}

      {/* Top unanswered questions */}
      {stats?.top_gaps?.length > 0 && filter === 'open' && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <TrendingUp size={18} className="text-amber-400" />
            <span>Most Asked Unanswered Queries</span>
          </h3>

          <div className="divide-y divide-slate-800">
            {stats.top_gaps.slice(0, 5).map((g, idx) => (
              <div 
                key={g.gap_id || idx} 
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-slate-500">#{idx + 1}</span>
                  <span className="text-xs font-semibold text-slate-300">{g.query}</span>
                </div>
                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <span className="inline-flex items-center rounded-full bg-amber-950/40 px-2 py-0.5 text-xxs font-bold text-amber-400 border border-amber-900/30">
                    {g.count}x
                  </span>
                  <button 
                    onClick={() => startResolve(g)}
                    className="px-3 py-1 bg-violet-600 hover:bg-violet-700 text-xxs font-semibold text-white rounded-lg shadow-sm cursor-pointer"
                  >
                    + Add FAQ
                  </button>
                  <button 
                    onClick={() => resolveGap(g.gap_id, 'dismiss')}
                    className="px-3 py-1 border border-slate-800 hover:bg-slate-800 text-xxs font-semibold text-slate-400 rounded-lg cursor-pointer"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Gaps List */}
      <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden divide-y divide-slate-800">
        {gaps.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <Sparkles size={40} className="text-violet-405 mx-auto mb-4 animate-pulse" />
            <h3 className="text-md font-bold text-white">No Knowledge Gaps</h3>
            <p className="text-xs text-slate-500 mt-2">
              {filter === 'open' ? 'Your bot is doing great! No unanswered customer questions logged.' : 'No items match the current filter.'}
            </p>
          </div>
        ) : (
          gaps.map((gap) => (
            <div key={gap.gap_id} className="p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold text-white">{gap.query}</h4>
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xxs font-bold uppercase ${STATUS_COLORS[gap.status] || 'bg-slate-950 text-slate-400 border border-slate-800'}`}>
                      {gap.status}
                    </span>
                    {gap.gap_type && (
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xxs font-bold ${
                        gap.gap_type === 'no_context' 
                          ? 'bg-rose-950/30 text-rose-400 border border-rose-900/30' 
                          : 'bg-amber-950/30 text-amber-400 border border-amber-900/30'
                      }`}>
                        {gap.gap_type === 'no_context' ? 'Knowledge Gap' : 'Out of Scope'}
                      </span>
                    )}
                  </div>
                  
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xxs font-semibold text-slate-500">
                    <span>Asked <strong className="text-slate-300">{gap.count}</strong> times</span>
                    {gap.url && <span className="truncate max-w-xs">on {new URL(gap.url).hostname}</span>}
                    <span>Last seen: {formatDate(gap.last_seen)}</span>
                  </div>

                  {/* Similar FAQs */}
                  {gap.similar_faqs && gap.similar_faqs.length > 0 && (
                    <div className="mt-2 p-2 bg-teal-950/20 rounded-lg border border-teal-900/30">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <LinkIcon size={12} className="text-teal-400" />
                        <span className="text-xxs font-bold text-teal-400">Similar FAQ Found ({gap.similar_faqs.length})</span>
                      </div>
                      <div className="space-y-1">
                        {gap.similar_faqs.map((faq, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-xxs">
                            <span className="text-slate-400 truncate max-w-xs">{faq.question}</span>
                            <span className="text-teal-500 font-mono">{Math.round(faq.similarity * 100)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-2 self-end sm:self-auto">
                  {gap.status === 'open' && (
                    <>
                      <button 
                        onClick={() => startResolve(gap)}
                        className="px-3.5 py-1.5 bg-violet-600 hover:bg-violet-700 text-xxs font-semibold text-white rounded-lg shadow-sm cursor-pointer"
                      >
                        + Answer
                      </button>
                      <button 
                        onClick={() => resolveGap(gap.gap_id, 'dismiss')}
                        className="px-3.5 py-1.5 border border-slate-800 hover:bg-slate-800 text-xxs font-semibold text-slate-400 rounded-lg cursor-pointer"
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Resolving form for this specific gap */}
              {resolving === gap.gap_id && (
                <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4 animate-slideUp">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white">Add FAQ Answer</span>
                    <button onClick={cancelResolve} className="text-slate-500 hover:text-slate-300 cursor-pointer">
                      <X size={16} />
                    </button>
                  </div>

                  <div className="space-y-3">
                    <input
                      value={faqForm.question}
                      onChange={(e) => setFaqForm((p) => ({ ...p, question: e.target.value }))}
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
                    />
                    <textarea
                      value={faqForm.answer}
                      onChange={(e) => setFaqForm((p) => ({ ...p, answer: e.target.value }))}
                      rows={3}
                      placeholder="Enter the answers that should be provided..."
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
                    />
                    <select
                      value={faqForm.source_id}
                      onChange={(e) => setFaqForm((p) => ({ ...p, source_id: e.target.value }))}
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-400 focus:border-violet-600 focus:outline-none transition-all cursor-pointer"
                    >
                      <option value="">Select a FAQ source...</option>
                      {sources.filter((s) => s.source_type === 'faq').map((s) => (
                        <option key={s.source_id} value={s.source_id}>{s.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => resolveGap(gap.gap_id, 'create_faq')}
                      disabled={!faqForm.question.trim() || !faqForm.answer.trim() || !faqForm.source_id}
                      className="px-4 py-2 bg-violet-600 text-xs font-semibold text-white rounded-lg shadow-sm hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                    >
                      Create & Index FAQ
                    </button>
                    <button onClick={cancelResolve} className="px-4 py-2 border border-slate-800 text-xs font-semibold text-slate-400 rounded-lg hover:bg-slate-800 cursor-pointer">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {total > 0 && (
          <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">
                Page {page} of {totalPages} ({total} total)
              </span>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="rounded-lg border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-400 focus:border-violet-600 focus:outline-none cursor-pointer"
              >
                <option value={20}>20 / page</option>
                <option value={50}>50 / page</option>
                <option value={100}>100 / page</option>
              </select>
            </div>
            {totalPages > 1 && (
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-semibold text-slate-400 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronLeft size={14} /> Prev
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-semibold text-slate-400 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default KnowledgeImprovement;