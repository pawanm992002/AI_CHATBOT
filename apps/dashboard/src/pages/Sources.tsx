import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { Source } from '../interfaces';
import { useStore, hasAccess } from '../store';
import { LoadingSpinner } from '@chatbot/shared';
import { useRbacError } from '../hooks/useRbacError';
import {
  Globe,
  FileText,
  HelpCircle,
  UploadCloud,
  Trash2,
  Plus,
  Layers,
  Calendar,
  AlertTriangle,
  Database,
  Lock,
  X,
  ExternalLink
} from 'lucide-react';

const TYPE_LABELS: Record<string, string> = {
  website: 'Website Urls',
  pdf: 'PDF Uploads',
  faq: 'FAQ Documents',
  text: 'Text Documents',
};

const TYPE_ICONS: Record<string, { icon: React.ComponentType<any>; color: string; bg: string }> = {
  website: { icon: Globe, color: 'text-blue-400', bg: 'bg-blue-950/40 border border-blue-900/40' },
  pdf: { icon: UploadCloud, color: 'text-rose-400', bg: 'bg-rose-950/40 border border-rose-900/40' },
  faq: { icon: HelpCircle, color: 'text-amber-400', bg: 'bg-amber-950/40 border border-amber-900/40' },
  text: { icon: FileText, color: 'text-violet-400', bg: 'bg-violet-950/40 border border-violet-900/40' },
};

interface DeleteModalProps {
  source: Source;
  onConfirm: (source: Source) => void;
  onCancel: () => void;
}

const DeleteModal = ({ source, onConfirm, onCancel }: DeleteModalProps) => {
  const [confirmName, setConfirmName] = useState('');
  const displayName = source.source_type === 'website' ? source.config?.seed_url : source.name;
  const matchName = source.source_type === 'website' ? source.config?.seed_url : source.name;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-md bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-800 flex flex-col text-slate-100">
        <div className="flex items-center gap-3 text-rose-400 mb-4">
          <AlertTriangle size={24} />
          <h3 className="text-lg font-bold text-white">Delete Knowledge Source</h3>
        </div>

        <p className="text-sm text-slate-400 mb-6 leading-relaxed">
          This will permanently delete <strong className="text-white">{displayName}</strong> and all its indexed vector data. This action cannot be undone.
        </p>

        <div className="space-y-2 mb-6">
          <label className="block text-xs font-semibold tracking-wider text-slate-500">
            Type <span className="text-slate-300 font-bold select-all">{matchName}</span> to confirm
          </label>
          <input
            type="text"
            placeholder={matchName}
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-650 focus:border-rose-500 focus:ring-2 focus:ring-rose-500/10 focus:outline-none transition-all duration-200"
            autoFocus
          />
        </div>

        <div className="flex gap-3 justify-end">
          <button
            className="px-5 py-2.5 rounded-xl border border-slate-800 text-sm font-semibold text-slate-400 hover:bg-slate-800 transition-colors cursor-pointer"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="px-5 py-2.5 rounded-xl bg-rose-600 text-sm font-semibold text-white shadow-sm hover:bg-rose-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            disabled={confirmName !== matchName}
            onClick={() => onConfirm(source)}
          >
            Permanently Delete
          </button>
        </div>
      </div>
    </div>
  );
};

const Sources = () => {
  const navigate = useNavigate();
  const { state } = useStore();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);
  const [pdfViewerSource, setPdfViewerSource] = useState<Source | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const { rbacError, triggerRbacError } = useRbacError();

  const isEditor = hasAccess(state.role, 'write');
  const isAdmin = hasAccess(state.role, 'delete');

  const fetchSources = async () => {
    try {
      const res = await privateAxios.get('/dashboard/sources');
      setSources(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSources();
  }, []);

  const handleDelete = async (source: Source) => {
    if (!isAdmin) {
      triggerRbacError("You do not have Administrator permissions to delete knowledge sources.");
      return;
    }
    try {
      const isCrawl = source.source_type === 'website';
      const url = isCrawl
        ? `/dashboard/sources/crawl/${source.config?.job_id || source.source_id.replace('crawl_', '')}`
        : `/dashboard/sources/${source.source_id}`;

      await privateAxios.delete(url);
      setDeleteTarget(null);
      fetchSources();
    } catch (err) {
      console.error(err);
    }
  };

  const createSource = async (type: string) => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to create knowledge sources.");
      return;
    }
    if (!newName.trim()) return;
    try {
      const res = await privateAxios.post('/dashboard/sources', {
        source_type: type,
        name: newName.trim(),
      });
      setShowCreate(null);
      setNewName('');
      if (type === 'faq') navigate(`/sources/faqs/${res.data.source_id}`);
      else if (type === 'text') navigate(`/sources/docs/${res.data.source_id}`);
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddWebsiteClick = () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to initiate website crawlers.");
    } else {
      navigate('/crawl');
    }
  };

  const handleUploadPdfClick = () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to upload PDFs.");
    } else {
      navigate('/sources/pdf');
    }
  };

  const handleCreateFaqClick = () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to add FAQ documents.");
    } else {
      setShowCreate('faq');
      setNewName('');
    }
  };

  const handleCreateTextClick = () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to add text documents.");
    } else {
      setShowCreate('text');
      setNewName('');
    }
  };

  const handleSourceRowClick = async (source: Source) => {
    if (source.source_type === 'faq') {
      navigate(`/sources/faqs/${source.source_id}`);
    } else if (source.source_type === 'text') {
      navigate(`/sources/docs/${source.source_id}`);
    } else if (source.source_type === 'pdf') {
      setPdfViewerSource(source);
      setPdfLoading(true);
      try {
        const res = await privateAxios.get(`/dashboard/sources/${source.source_id}/pdf_url`);
        setPdfUrl(res.data.url);
      } catch (err) {
        console.error(err);
        setPdfViewerSource(null);
      } finally {
        setPdfLoading(false);
      }
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading sources..." />;
  }

  const sourcesByType: Record<string, Source[]> = {};
  for (const s of sources) {
    const type = s.source_type || 'other';
    if (!sourcesByType[type]) sourcesByType[type] = [];
    sourcesByType[type].push(s);
  }

  const orderedTypes = ['website', 'pdf', 'faq', 'text'];

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header section */}
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Knowledge Sources</h2>
          <p className="text-slate-400 text-sm mt-1">
            Provide the datasets your AI assistant answers from. Add, edit, or sync crawl jobs.
          </p>
        </div>

        {/* Quick add actions */}
        <div className="flex flex-wrap gap-2.5">
          <button
            onClick={handleAddWebsiteClick}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-violet-600 text-sm font-semibold text-white shadow-md shadow-violet-900/30 hover:bg-violet-700 transition-all cursor-pointer"
          >
            <Plus size={16} />
            <span>Add Website</span>
          </button>
          <button
            onClick={handleUploadPdfClick}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-850 text-sm font-semibold text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <UploadCloud size={16} className="text-rose-400" />
            <span>Upload PDF</span>
          </button>
          <button
            onClick={handleCreateFaqClick}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-850 text-sm font-semibold text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <Plus size={16} className="text-amber-400" />
            <span>FAQ Document</span>
          </button>
          <button
            onClick={handleCreateTextClick}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-850 text-sm font-semibold text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <Plus size={16} className="text-indigo-400" />
            <span>Text Document</span>
          </button>
        </div>
      </div>

      {/* RBAC Error Banner */}
      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/40 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      {/* Creation card */}
      {showCreate && (
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4 animate-slideUp">
          <h3 className="text-sm font-bold text-white">
            Create New {TYPE_LABELS[showCreate]} Source
          </h3>
          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex-1 space-y-2 w-full">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                Source Document Name
              </label>
              <input
                placeholder="e.g. Admission Guidelines"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createSource(showCreate)}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
                autoFocus
              />
            </div>
            <div className="flex gap-2 w-full sm:w-auto">
              <button
                onClick={() => createSource(showCreate)}
                disabled={!newName.trim()}
                className="flex-1 sm:flex-none px-5 py-2.5 bg-violet-600 text-sm font-semibold text-white rounded-xl shadow-sm hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Create
              </button>
              <button
                onClick={() => setShowCreate(null)}
                className="flex-1 sm:flex-none px-5 py-2.5 border border-slate-800 text-sm font-semibold text-slate-400 rounded-xl hover:bg-slate-800 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {sources.length === 0 && (
        <div className="bg-slate-900 px-6 py-16 rounded-3xl border border-slate-800/80 shadow-lg text-center max-w-xl mx-auto">
          <Database size={44} className="text-slate-700 mx-auto mb-4 animate-pulse" />
          <h3 className="text-lg font-bold text-white">No Knowledge Sources</h3>
          <p className="text-sm text-slate-400 mt-2 max-w-sm mx-auto leading-relaxed">
            Create a website crawler, upload a file, or create custom FAQs to bootstrap your chatbot's intelligence.
          </p>
        </div>
      )}

      {/* Sources list */}
      <div className="space-y-8">
        {orderedTypes.map((type) => {
          const items = sourcesByType[type] || [];
          if (items.length === 0) return null;
          const config = TYPE_ICONS[type];
          const Icon = config.icon;

          return (
            <div key={type} className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 px-1">
                {TYPE_LABELS[type]} ({items.length})
              </h3>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((source) => {
                  const isWebsite = source.source_type === 'website';
                  const displayName = isWebsite ? source.config?.seed_url : source.name;
                  const canClick = source.source_type === 'faq' || source.source_type === 'text' || source.source_type === 'pdf';

                  return (
                    <div
                      key={source.source_id}
                      className={`bg-slate-900 p-5 rounded-3xl border border-slate-800/80 shadow-sm hover:shadow-lg transition-all flex flex-col justify-between ${canClick ? 'cursor-pointer hover:border-slate-700' : ''
                        }`}
                      onClick={() => canClick && handleSourceRowClick(source)}
                    >
                      <div className="flex items-start gap-4">
                        <div className={`h-10 w-10 rounded-xl flex items-center justify-center flex-shrink-0 ${config.bg} ${config.color}`}>
                          <Icon size={20} />
                        </div>

                        <div className="min-w-0 space-y-1">
                          <h4
                            className="text-sm font-bold text-white truncate"
                            title={displayName}
                          >
                            {displayName}
                          </h4>
                          <div className="flex items-center gap-1.5 text-xxs font-medium text-slate-500">
                            <Layers size={12} />
                            <span>{source.chunk_count || 0} chunks</span>
                            {source.last_indexed_at && (
                              <>
                                <span>·</span>
                                <Calendar size={12} />
                                <span>{formatDate(source.last_indexed_at)}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="mt-5 pt-4 border-t border-slate-800 flex items-center justify-between" onClick={(e) => e.stopPropagation()}>
                        <span className="inline-flex items-center rounded-full bg-teal-950/40 px-2.5 py-0.5 text-xxs font-bold text-teal-400 border border-teal-900/30">
                          Active
                        </span>

                        {isAdmin ? (
                          <button
                            onClick={() => setDeleteTarget(source)}
                            className="p-2 text-slate-500 hover:text-rose-400 hover:bg-rose-950/20 rounded-lg transition-colors cursor-pointer"
                            title="Delete Source"
                          >
                            <Trash2 size={16} />
                          </button>
                        ) : (
                          <span className="p-2 text-slate-700" title="Delete restricted to admin only">
                            <Lock size={14} />
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {deleteTarget && (
        <DeleteModal
          source={deleteTarget}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {pdfViewerSource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-5xl h-[85vh] bg-slate-900 rounded-3xl border border-slate-800 shadow-2xl flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <FileText size={18} className="text-rose-400" />
                <h3 className="text-sm font-bold text-white truncate max-w-md">{pdfViewerSource.name}</h3>
              </div>
              <div className="flex items-center gap-2">
                {pdfUrl && (
                  <a
                    href={pdfUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                  >
                    <ExternalLink size={14} />
                    <span>Open in new tab</span>
                  </a>
                )}
                <button
                  onClick={() => { setPdfViewerSource(null); setPdfUrl(null); }}
                  className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {pdfLoading ? (
                <div className="flex items-center justify-center h-full">
                  <LoadingSpinner message="Loading PDF..." />
                </div>
              ) : pdfUrl ? (
                <iframe
                  src={pdfUrl}
                  className="w-full h-full border-0"
                  title={pdfViewerSource.name}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                  Failed to load PDF
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Sources;
