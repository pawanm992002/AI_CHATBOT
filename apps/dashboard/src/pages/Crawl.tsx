import { useState, useEffect } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { useStore, hasAccess } from '../store';
import { useRbacError } from '../hooks/useRbacError';
import { RefreshCw, AlertCircle, History, Play, Lock, ChevronLeft, ChevronRight, XCircle } from 'lucide-react';

const Crawl = () => {
  const { state } = useStore();
  const [seedUrl, setSeedUrl] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [crawlError, setCrawlError] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const { rbacError, triggerRbacError } = useRbacError();
  const pageSize = 20;

  const isEditor = hasAccess(state.role, 'write');

  const fetchHistory = async (p: number) => {
    setIsLoading(true);
    try {
      const res = await privateAxios.get(`/dashboard/crawl/history?page=${p}&page_size=${pageSize}`);
      const data = res.data;
      const items = Array.isArray(data.items) ? data.items : [];
      setHistory(items);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);

      // Auto-track any running job on page load (only first page)
      if (p === 1 && !jobId) {
        const activeJob = items.find((j: any) =>
          j.status === 'running' || j.status === 'processing' || j.status === 'queued'
        );
        if (activeJob) {
          setJobId(activeJob.job_id);
          setJobStatus(activeJob);
        }
      }
    } catch (err) {
      console.error('Failed to fetch crawl history:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory(page);
  }, [page]);

  const handleCrawl = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to launch web crawlers.");
      return;
    }
    if (!seedUrl || isStarting) return;
    setIsStarting(true);
    setCrawlError('');
    try {
      const res = await privateAxios.post('/dashboard/crawl', { seed_url: seedUrl });
      setJobId(res.data.job_id);
      setJobStatus(null);
      setSeedUrl('');
      setPage(1);
      fetchHistory(1);
    } catch (err: any) {
      setCrawlError(err.response?.data?.detail || 'Failed to start crawl job');
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancel = async (targetJobId?: string) => {
    const id = targetJobId || jobId;
    if (!id || isCancelling) return;
    setIsCancelling(true);
    try {
      await privateAxios.delete(`/dashboard/crawl/${id}`);
      if (id === jobId) {
        setJobStatus((prev: any) => prev ? { ...prev, status: 'failed', error: 'Cancelled by user' } : prev);
      }
      setPage(1);
      fetchHistory(1);
    } catch (err: any) {
      setCrawlError(err.response?.data?.detail || 'Failed to cancel crawl job');
    } finally {
      setIsCancelling(false);
    }
  };

  useEffect(() => {
    let interval: any;
    if (jobId) {
      interval = setInterval(async () => {
        try {
          const res = await privateAxios.get(`/dashboard/crawl/${jobId}`);
          setJobStatus(res.data);
          if (res.data.status === 'done' || res.data.status === 'failed') {
            clearInterval(interval);
            setPage(1);
            fetchHistory(1);
          }
        } catch {
          clearInterval(interval);
        }
      }, 5000);
    }
    return () => clearInterval(interval);
  }, [jobId]);

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Website Crawler</h2>
        <p className="text-slate-400 text-sm mt-1">
          Index entire websites page-by-page. Content is extracted, chunked, and embedded into the search database.
        </p>
      </div>

      {/* RBAC Error Banner */}
      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/40 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-3">
        {/* Crawler Input Box */}
        <div className="md:col-span-2 bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-5">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Play size={18} className="text-violet-400" />
            <span>Launch Web Crawler</span>
          </h3>

          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex-1 space-y-2 w-full">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                Seed URL
              </label>
              <input
                type="url"
                placeholder="https://example.com"
                value={seedUrl}
                onChange={(e) => {
                  setSeedUrl(e.target.value);
                  setCrawlError('');
                }}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
              />
            </div>
            <button
              onClick={handleCrawl}
              disabled={isStarting || !seedUrl.trim()}
              className="w-full sm:w-auto px-5 py-2.5 bg-violet-600 text-sm font-semibold text-white rounded-xl shadow-md hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-1.5"
            >
              {!isEditor && <Lock size={14} />}
              <span>{isStarting ? 'Starting...' : 'Start Crawl'}</span>
            </button>
          </div>

          {crawlError && (
            <div className="flex items-start gap-3 rounded-xl bg-rose-950/40 p-4 text-sm text-rose-350 border border-rose-900/60">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{crawlError}</span>
            </div>
          )}
        </div>

        {/* Tip Guidelines Card */}
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg h-fit space-y-4">
          <h3 className="text-sm font-bold text-white">Crawl Settings</h3>
          <ul className="text-xs text-slate-400 space-y-3 leading-relaxed">
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Ensure the seed URL is accessible and not behind authentication.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Crawls will respect standard subpath boundaries and follow internal links.</span>
            </li>
          </ul>
        </div>
      </div>

      {/* Active Job Tracker */}
      {jobStatus && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4 animate-slideUp">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white">Active Crawl Progress</h3>
            <div className="flex items-center gap-2">
              {(jobStatus.status === 'running' || jobStatus.status === 'processing' || jobStatus.status === 'queued') && (
                <button
                  onClick={() => handleCancel()}
                  disabled={isCancelling}
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xxs font-bold uppercase bg-rose-950/40 text-rose-400 border border-rose-900/30 hover:bg-rose-950/60 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-all"
                >
                  <XCircle size={14} />
                  {isCancelling ? 'Cancelling...' : 'Cancel'}
                </button>
              )}
              <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xxs font-bold uppercase ${jobStatus.status === 'done'
                  ? 'bg-teal-950/40 text-teal-400 border border-teal-900/30'
                  : jobStatus.status === 'failed'
                    ? 'bg-rose-950/40 text-rose-400 border border-rose-900/30'
                    : 'bg-amber-950/40 text-amber-400 border border-amber-900/30 animate-pulse'
                }`}>
                {jobStatus.status}
              </span>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 text-xs">
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-850">
              <span className="block text-slate-500 font-semibold mb-0.5">Seed URL</span>
              <span className="block text-slate-300 font-medium truncate">{jobStatus.seed_url}</span>
            </div>
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-850">
              <span className="block text-slate-500 font-semibold mb-0.5">Pages Crawled</span>
              <span className="block text-white font-bold text-lg">{jobStatus.pages_found}</span>
            </div>
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-850">
              <span className="block text-slate-500 font-semibold mb-0.5">Chunks Indexed</span>
              <span className="block text-white font-bold text-lg">{jobStatus.chunks_created}</span>
            </div>
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-850">
              <span className="block text-slate-500 font-semibold mb-0.5">Started At</span>
              <span className="block text-slate-400 font-medium">{formatDate(jobStatus.started_at)}</span>
            </div>
          </div>

          {jobStatus.error && (
            <div className="flex items-start gap-3 rounded-xl bg-rose-950/20 p-4 text-xs text-rose-350 border border-rose-900/50">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{jobStatus.error}</span>
            </div>
          )}
        </div>
      )}

      {/* Crawl History */}
      <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-800 flex items-center gap-2">
          <History size={18} className="text-violet-400" />
          <h3 className="text-sm font-bold text-white">Crawl History</h3>
        </div>

        {history.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <RefreshCw size={36} className={`text-slate-700 mx-auto mb-3 ${isLoading ? 'animate-spin' : ''}`} />
            <h4 className="text-sm font-bold text-white">No crawls recorded</h4>
            <p className="text-xs text-slate-500 mt-1">Start your first crawler above.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 text-xxs font-bold uppercase tracking-wider bg-slate-950/60">
                  <th className="px-6 py-3.5">Seed URL</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Actions</th>
                  <th className="px-6 py-3.5">Pages</th>
                  <th className="px-6 py-3.5">Chunks</th>
                  <th className="px-6 py-3.5">Started</th>
                  <th className="px-6 py-3.5">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs text-slate-300">
                {history.map((job, idx) => (
                  <tr key={idx} className="hover:bg-slate-950/40 transition-colors">
                    <td className="px-6 py-4 font-semibold text-slate-200 max-w-xs truncate" title={job.seed_url}>
                      {job.seed_url}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xxs font-bold uppercase ${job.status === 'done'
                          ? 'bg-teal-950/40 text-teal-400 border border-teal-900/30'
                          : job.status === 'failed' || job.status === 'purged'
                            ? 'bg-rose-950/40 text-rose-400 border border-rose-900/30'
                            : 'bg-amber-950/40 text-amber-400 border border-amber-900/30'
                        }`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {(job.status === 'running' || job.status === 'processing' || job.status === 'queued') && (
                        <button
                          onClick={() => handleCancel(job.job_id)}
                          disabled={isCancelling}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xxs font-bold uppercase bg-rose-950/40 text-rose-400 border border-rose-900/30 hover:bg-rose-950/60 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-all"
                        >
                          <XCircle size={12} />
                          {isCancelling ? '...' : 'Cancel'}
                        </button>
                      )}
                    </td>
                    <td className="px-6 py-4 font-bold text-white">{job.pages_found}</td>
                    <td className="px-6 py-4 font-bold text-white">{job.chunks_created}</td>
                    <td className="px-6 py-4 text-slate-400">{formatDate(job.started_at)}</td>
                    <td className="px-6 py-4 text-slate-400">{formatDate(job.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Page {page} of {totalPages} ({total} total)
                </span>
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
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Crawl;