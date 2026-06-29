import { useState, useEffect, useMemo } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { useStore, hasAccess } from '../store';
import { useRbacError } from '../hooks/useRbacError';
import {
  RefreshCw, AlertCircle, History, Play, Lock, ChevronLeft, ChevronRight,
  Search, CheckSquare, Square, Loader2, Globe, ChevronDown, ChevronRight as ChevronRightIcon,
  FolderOpen, FileText, Globe2,
} from 'lucide-react';

function categorizeUrl(url: string, seedHost: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname;
    if (!path || path === '/') return 'Home';
    const segments = path.split('/').filter(Boolean);
    if (segments.length === 0) return 'Home';
    if (segments[0] === 'blogs') return 'Blogs';
    if (segments[0] === 'courses') return 'Courses';
    if (segments[0] === 'about') return 'About';
    if (segments[0] === 'contact') return 'Contact';
    if (segments[0] === 'results') return 'Results';
    if (segments[0] === 'latest') return 'Latest';
    if (segments[0] === 'schooling') return 'Schooling';
    if (segments[0] === 'gsat') return 'GSAT';
    if (segments[0] === 'refund-rules') return 'Policies';
    if (segments[0] === 'Privacy-and-Policy') return 'Policies';
    if (segments[0] === 'Terms-of-Services') return 'Policies';
    return segments[0].charAt(0).toUpperCase() + segments[0].slice(1);
  } catch {
    return 'Other';
  }
}

function getPathPreview(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.pathname + parsed.hash;
  } catch {
    return url;
  }
}

const Crawl = () => {
  const { state } = useStore();
  const [seedUrl, setSeedUrl] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [isStarting, setIsStarting] = useState(false);
  const [crawlError, setCrawlError] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const { rbacError, triggerRbacError } = useRbacError();
  const pageSize = 20;

  // URL discovery state
  const [discoveredUrls, setDiscoveredUrls] = useState<string[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState('');
  const [discoveryDone, setDiscoveryDone] = useState(false);
  const [urlSearch, setUrlSearch] = useState('');
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  const isEditor = hasAccess(state.role, 'write');

  // Extract host from seed URL for categorization
  const seedHost = useMemo(() => {
    try {
      return new URL(seedUrl.startsWith('http') ? seedUrl : `https://${seedUrl}`).hostname;
    } catch {
      return '';
    }
  }, [seedUrl]);

  // Group URLs by category
  const groupedUrls = useMemo(() => {
    const groups: Record<string, string[]> = {};
    for (const url of discoveredUrls) {
      const cat = categorizeUrl(url, seedHost);
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(url);
    }
    // Sort: Home first, then alphabetical
    const sortedKeys = Object.keys(groups).sort((a, b) => {
      if (a === 'Home') return -1;
      if (b === 'Home') return 1;
      return a.localeCompare(b);
    });
    return sortedKeys.map(key => ({ category: key, urls: groups[key] }));
  }, [discoveredUrls, seedHost]);

  // Filtered groups based on search
  const filteredGroups = useMemo(() => {
    if (!urlSearch) return groupedUrls;
    const q = urlSearch.toLowerCase();
    return groupedUrls
      .map(g => ({
        ...g,
        urls: g.urls.filter(u => u.toLowerCase().includes(q)),
      }))
      .filter(g => g.urls.length > 0);
  }, [groupedUrls, urlSearch]);

  const fetchHistory = async (p: number) => {
    try {
      const res = await privateAxios.get(`/dashboard/crawl/history?page=${p}&page_size=${pageSize}`);
      const data = res.data;
      setHistory(Array.isArray(data.items) ? data.items : []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch (err) {
      console.error('Failed to fetch crawl history:', err);
    }
  };

  useEffect(() => {
    fetchHistory(page);
  }, [page]);

  const handleDiscover = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to launch web crawlers.");
      return;
    }
    if (!seedUrl.trim() || isDiscovering) return;
    setIsDiscovering(true);
    setDiscoverError('');
    setDiscoveredUrls([]);
    setSelectedUrls(new Set());
    setDiscoveryDone(false);
    try {
      const res = await privateAxios.post('/dashboard/crawl/discover', { seed_url: seedUrl });
      const urls: string[] = res.data.urls || [];
      setDiscoveredUrls(urls);
      setSelectedUrls(new Set(urls));
      setDiscoveryDone(true);
    } catch (err: any) {
      setDiscoverError(err.response?.data?.detail || 'Failed to discover URLs');
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleCrawl = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to launch web crawlers.");
      return;
    }
    const urlsToCrawl = Array.from(selectedUrls);
    if (!seedUrl.trim() || urlsToCrawl.length === 0 || isStarting) return;
    setIsStarting(true);
    setCrawlError('');
    try {
      const res = await privateAxios.post('/dashboard/crawl', {
        seed_url: seedUrl,
        urls: urlsToCrawl,
      });
      setJobId(res.data.job_id);
      setJobStatus(null);
      setDiscoveredUrls([]);
      setSelectedUrls(new Set());
      setDiscoveryDone(false);
      setSeedUrl('');
      setPage(1);
      fetchHistory(1);
    } catch (err: any) {
      setCrawlError(err.response?.data?.detail || 'Failed to start crawl job');
    } finally {
      setIsStarting(false);
    }
  };

  const toggleUrl = (url: string) => {
    setSelectedUrls(prev => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const toggleCategory = (urls: string[]) => {
    setSelectedUrls(prev => {
      const next = new Set(prev);
      const allSelected = urls.every(u => next.has(u));
      if (allSelected) {
        urls.forEach(u => next.delete(u));
      } else {
        urls.forEach(u => next.add(u));
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedUrls.size === discoveredUrls.length) {
      setSelectedUrls(new Set());
    } else {
      setSelectedUrls(new Set(discoveredUrls));
    }
  };

  const toggleCollapsed = (cat: string) => {
    setCollapsedCategories(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
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
          Discover URLs, select which to crawl, then index content into the search database.
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
                  setDiscoverError('');
                  setDiscoveryDone(false);
                  setDiscoveredUrls([]);
                  setSelectedUrls(new Set());
                }}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
              />
            </div>
            <button
              onClick={handleDiscover}
              disabled={isDiscovering || !seedUrl.trim() || !isEditor}
              className="w-full sm:w-auto px-5 py-2.5 bg-slate-700 text-sm font-semibold text-white rounded-xl shadow-md hover:bg-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-1.5"
            >
              {!isEditor && <Lock size={14} />}
              {isDiscovering ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Discovering...</span>
                </>
              ) : (
                <>
                  <Search size={14} />
                  <span>Discover URLs</span>
                </>
              )}
            </button>
          </div>

          {discoverError && (
            <div className="flex items-start gap-3 rounded-xl bg-rose-950/40 p-4 text-sm text-rose-350 border border-rose-900/60">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{discoverError}</span>
            </div>
          )}

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
              <span>Discover URLs first, then select which pages to crawl.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Use category toggles to quickly select/deselect entire groups.</span>
            </li>
          </ul>
        </div>
      </div>

      {/* Discovered URLs Panel */}
      {discoveryDone && discoveredUrls.length > 0 && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4 animate-slideUp">
          {/* Header row */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Globe size={18} className="text-violet-400" />
              <h3 className="text-sm font-bold text-white">
                Discovered URLs
              </h3>
              <span className="text-xs text-slate-400 font-medium">
                {selectedUrls.size}/{discoveredUrls.length} selected
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={toggleAll}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer"
              >
                {selectedUrls.size === discoveredUrls.length ? 'Deselect All' : 'Select All'}
              </button>
              <button
                onClick={handleCrawl}
                disabled={isStarting || selectedUrls.size === 0}
                className="px-4 py-1.5 bg-violet-600 text-xs font-semibold text-white rounded-xl shadow-md hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-1.5"
              >
                {isStarting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Starting...</span>
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    <span>Crawl Selected ({selectedUrls.size})</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Search filter */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Filter URLs..."
              value={urlSearch}
              onChange={(e) => setUrlSearch(e.target.value)}
              className="w-full rounded-xl border border-slate-800 bg-slate-950 pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
            />
          </div>

          {/* Category groups */}
          <div className="max-h-[32rem] overflow-y-auto space-y-2 pr-1 scrollbar-thin">
            {filteredGroups.map(({ category, urls }) => {
              const selectedCount = urls.filter(u => selectedUrls.has(u)).length;
              const allSelected = selectedCount === urls.length;
              const someSelected = selectedCount > 0 && !allSelected;
              const isCollapsed = collapsedCategories.has(category);

              return (
                <div key={category} className="border border-slate-800/60 rounded-xl overflow-hidden">
                  {/* Category header */}
                  <div
                    className="flex items-center gap-3 px-3 py-2.5 bg-slate-950/60 cursor-pointer hover:bg-slate-950/80 transition-colors select-none"
                    onClick={() => toggleCollapsed(category)}
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleCategory(urls);
                      }}
                      className="flex-shrink-0 cursor-pointer"
                      title={allSelected ? `Deselect all ${category}` : `Select all ${category}`}
                    >
                      {allSelected ? (
                        <CheckSquare size={16} className="text-violet-400" />
                      ) : someSelected ? (
                        <div className="w-4 h-4 rounded border-2 border-violet-400 bg-violet-400/20 flex items-center justify-center">
                          <div className="w-2 h-0.5 bg-violet-400 rounded" />
                        </div>
                      ) : (
                        <Square size={16} className="text-slate-600" />
                      )}
                    </button>

                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      {category === 'Blogs' ? (
                        <FileText size={14} className="text-slate-500 flex-shrink-0" />
                      ) : category === 'Home' ? (
                        <Globe2 size={14} className="text-slate-500 flex-shrink-0" />
                      ) : (
                        <FolderOpen size={14} className="text-slate-500 flex-shrink-0" />
                      )}
                      <span className="text-xs font-bold text-slate-200">{category}</span>
                      <span className="text-xxs text-slate-500 font-medium">
                        {selectedCount}/{urls.length}
                      </span>
                    </div>

                    {isCollapsed ? (
                      <ChevronRightIcon size={14} className="text-slate-600 flex-shrink-0" />
                    ) : (
                      <ChevronDown size={14} className="text-slate-600 flex-shrink-0" />
                    )}
                  </div>

                  {/* URL list (collapsible) */}
                  {!isCollapsed && (
                    <div className="divide-y divide-slate-800/40">
                      {urls.map((url, idx) => (
                        <label
                          key={idx}
                          className="flex items-center gap-3 px-3 py-2 pl-8 hover:bg-slate-950/40 cursor-pointer transition-colors group"
                        >
                          <input
                            type="checkbox"
                            checked={selectedUrls.has(url)}
                            onChange={() => toggleUrl(url)}
                            className="sr-only"
                          />
                          {selectedUrls.has(url) ? (
                            <CheckSquare size={14} className="text-violet-400 flex-shrink-0" />
                          ) : (
                            <Square size={14} className="text-slate-600 group-hover:text-slate-500 flex-shrink-0" />
                          )}
                          <span className="text-xs text-slate-400 truncate font-mono" title={url}>
                            {getPathPreview(url)}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {filteredGroups.length === 0 && urlSearch && (
              <div className="text-center py-4 text-xs text-slate-500">
                No URLs match "{urlSearch}"
              </div>
            )}
          </div>
        </div>
      )}

      {discoveryDone && discoveredUrls.length === 0 && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg text-center">
          <Globe size={36} className="text-slate-700 mx-auto mb-3" />
          <h4 className="text-sm font-bold text-white">No URLs found</h4>
          <p className="text-xs text-slate-500 mt-1">The sitemap returned no URLs for this seed URL.</p>
        </div>
      )}

      {/* Active Job Tracker */}
      {jobStatus && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4 animate-slideUp">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white">Active Crawl Progress</h3>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xxs font-bold uppercase ${
              jobStatus.status === 'done'
                ? 'bg-teal-950/40 text-teal-400 border border-teal-900/30'
                : jobStatus.status === 'failed'
                ? 'bg-rose-950/40 text-rose-400 border border-rose-900/30'
                : 'bg-amber-950/40 text-amber-400 border border-amber-900/30 animate-pulse'
            }`}>
              {jobStatus.status}
            </span>
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
            <RefreshCw size={36} className="text-slate-700 mx-auto mb-3 animate-spin" />
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
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xxs font-bold uppercase ${
                        job.status === 'done'
                          ? 'bg-teal-950/40 text-teal-400 border border-teal-900/30'
                          : job.status === 'failed' || job.status === 'purged'
                          ? 'bg-rose-950/40 text-rose-400 border border-rose-900/30'
                          : 'bg-amber-950/40 text-amber-400 border border-amber-900/30'
                      }`}>
                        {job.status}
                      </span>
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
