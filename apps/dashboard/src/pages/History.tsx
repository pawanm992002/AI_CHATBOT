import { useState, useEffect } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { SourceJob, PaginatedResponse } from '../interfaces';
import { History as HistoryIcon, Globe, FileText, HelpCircle, UploadCloud, AlertCircle, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { LoadingSpinner } from '@chatbot/shared';

const JOB_TYPE_LABELS: Record<string, string> = {
  crawl: 'Website Crawl',
  pdf_index: 'PDF Index',
  faq_index: 'FAQ Index',
  text_index: 'Text Index',
};

const JOB_TYPE_ICONS: Record<string, React.ComponentType<any>> = {
  crawl: Globe,
  pdf_index: UploadCloud,
  faq_index: HelpCircle,
  text_index: FileText,
};

const STATUS_STYLES: Record<string, string> = {
  done: 'bg-teal-950/40 text-teal-400 border border-teal-900/30',
  failed: 'bg-rose-950/40 text-rose-400 border border-rose-900/30',
  running: 'bg-amber-950/40 text-amber-400 border border-amber-900/30 animate-pulse',
  queued: 'bg-slate-800 text-slate-400 border border-slate-700',
  purged: 'bg-slate-950/60 text-slate-500 border border-slate-800 line-through',
};

const History = () => {
  const [jobs, setJobs] = useState<SourceJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  const fetchHistory = async (p: number) => {
    try {
      const res = await privateAxios.get<PaginatedResponse<SourceJob>>(`/dashboard/sources/history?page=${p}&page_size=${pageSize}`);
      setJobs(res.data.items);
      setTotal(res.data.total);
      setTotalPages(res.data.total_pages);
    } catch (err) {
      console.error('Failed to fetch source history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory(page);
  }, [page]);

  if (loading) {
    return <LoadingSpinner message="Loading audit history..." />;
  }

  return (
    <div className="space-y-6 text-slate-100 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Index Audit History</h2>
        <p className="text-slate-400 text-sm mt-1">
          Track all indexing operations across websites, PDFs, FAQs, and text documents.
        </p>
      </div>

      {jobs.length === 0 ? (
        <div className="bg-slate-900 px-6 py-16 rounded-3xl border border-slate-800/80 shadow-lg text-center max-w-xl mx-auto">
          <HistoryIcon size={44} className="text-slate-700 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-white">No History</h3>
          <p className="text-sm text-slate-400 mt-2 max-w-sm mx-auto leading-relaxed">
            Indexing jobs will appear here once you add knowledge sources.
          </p>
        </div>
      ) : (
        <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 text-xxs font-bold uppercase tracking-wider bg-slate-950/60">
                  <th className="px-6 py-3.5">Type</th>
                  <th className="px-6 py-3.5">Source ID</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Chunks</th>
                  <th className="px-6 py-3.5">Errors</th>
                  <th className="px-6 py-3.5">Started</th>
                  <th className="px-6 py-3.5">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs text-slate-300">
                {jobs.map((job) => {
                  const Icon = JOB_TYPE_ICONS[job.job_type] || Globe;
                  return (
                    <tr key={job.job_id} className="hover:bg-slate-950/40 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <Icon size={14} className="text-slate-500" />
                          <span className="font-semibold text-slate-200">{JOB_TYPE_LABELS[job.job_type] || job.job_type}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-slate-400 font-mono text-xxs max-w-[120px] truncate" title={job.source_id}>
                        {job.source_id.substring(0, 12)}...
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xxs font-bold uppercase ${STATUS_STYLES[job.status] || 'bg-slate-800 text-slate-400'}`}>
                          {job.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-bold text-white">{job.chunks_created}</td>
                      <td className="px-6 py-4">
                        {job.embedding_errors > 0 ? (
                          <span className="text-rose-400 font-semibold">{job.embedding_errors}</span>
                        ) : (
                          <span className="text-slate-600">0</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-slate-400">{formatDate(job.started_at)}</td>
                      <td className="px-6 py-4 text-slate-400">{formatDate(job.finished_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

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
  );
};

export default History;
