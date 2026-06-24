import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { FAQ, Source } from '../interfaces';
import { useStore, hasAccess } from '../store';
import { LoadingSpinner } from '@chatbot/shared';
import { useRbacError } from '../hooks/useRbacError';
import { 
  ArrowLeft, 
  HelpCircle, 
  Trash2, 
  Edit3, 
  Plus, 
  RefreshCw,
  Save,
  X,
  Lock
} from 'lucide-react';

const FAQs = () => {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const { state } = useStore();
  const [source, setSource] = useState<Source | null>(null);
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editQuestion, setEditQuestion] = useState('');
  const [editAnswer, setEditAnswer] = useState('');
  const [indexing, setIndexing] = useState(false);
  const { rbacError, triggerRbacError } = useRbacError();

  const isEditor = hasAccess(state.role, 'write');
  const isAdmin = hasAccess(state.role, 'delete');

  const fetchData = React.useCallback(async () => {
    try {
      const [sourceRes, faqsRes] = await Promise.all([
        privateAxios.get(`/dashboard/sources/${sourceId}`),
        privateAxios.get(`/dashboard/sources/${sourceId}/faqs`),
      ]);

      if (sourceRes.data.source_type !== 'faq') {
        navigate('/sources');
        return;
      }
      setSource(sourceRes.data);
      setFaqs(faqsRes.data);
    } catch (err) {
      console.error(err);
      navigate('/sources');
    } finally {
      setLoading(false);
    }
  }, [sourceId, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const addFaq = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to add FAQ entries.");
      return;
    }
    if (!newQuestion.trim() || !newAnswer.trim()) return;
    try {
      await privateAxios.post(`/dashboard/sources/${sourceId}/faqs`, {
        question: newQuestion.trim(),
        answer: newAnswer.trim(),
      });
      setNewQuestion('');
      setNewAnswer('');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const updateFaq = async (faqId: string) => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to update FAQ entries.");
      return;
    }
    if (!editQuestion.trim() || !editAnswer.trim()) return;
    try {
      await privateAxios.put(`/dashboard/sources/${sourceId}/faqs/${faqId}`, {
        question: editQuestion.trim(),
        answer: editAnswer.trim(),
      });
      setEditingId(null);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const deleteFaq = async (faqId: string) => {
    if (!isAdmin) {
      triggerRbacError("You do not have Administrator permissions to delete FAQ entries.");
      return;
    }
    if (!window.confirm('Delete this FAQ?')) return;
    try {
      await privateAxios.delete(`/dashboard/sources/${sourceId}/faqs/${faqId}`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const indexFaqs = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to sync or index FAQ documents.");
      return;
    }
    setIndexing(true);
    try {
      await privateAxios.post(`/dashboard/sources/${sourceId}/faqs/index`);
      const poll = setInterval(async () => {
        try {
          const sr = await privateAxios.get(`/dashboard/sources/${sourceId}`);
          setSource(sr.data);
          if (sr.data.status !== 'indexing') {
            clearInterval(poll);
            setIndexing(false);
            fetchData();
          }
        } catch {
          clearInterval(poll);
          setIndexing(false);
        }
      }, 2000);
    } catch {
      setIndexing(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading FAQs..." />;
  }

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/sources')}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-bold text-white tracking-tight">{source?.name || 'FAQs'}</h2>
              {source && (
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xxs font-bold uppercase ${
                  source.status === 'ready' 
                    ? 'bg-teal-950/40 text-teal-400 border border-teal-900/30' 
                    : source.status === 'indexing' 
                    ? 'bg-amber-950/40 text-amber-400 border border-amber-900/30 animate-pulse' 
                    : 'bg-rose-950/40 text-rose-400 border border-rose-900/30'
                }`}>
                  {source.status}
                </span>
              )}
            </div>
            {source && (
              <p className="text-xs text-slate-400 mt-1">
                {faqs.length} FAQ Q&As · {source.chunk_count || 0} chunks indexed
                {source.last_indexed_at && ` · Last indexed: ${formatDate(source.last_indexed_at)}`}
              </p>
            )}
          </div>
        </div>

        {/* Index Action */}
        <button
          onClick={indexFaqs}
          disabled={indexing || faqs.length === 0}
          className="flex items-center justify-center gap-2 px-5 py-2.5 bg-violet-600 text-sm font-semibold text-white rounded-xl shadow-md shadow-violet-900/30 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          <RefreshCw size={16} className={indexing ? 'animate-spin' : ''} />
          <span>{indexing ? 'Indexing FAQs...' : 'Sync & Index FAQs'}</span>
        </button>
      </div>

      {/* RBAC Warning Banner */}
      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/40 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Add FAQ form */}
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg h-fit space-y-5">
          <h3 className="text-md font-bold text-white flex items-center gap-2">
            <Plus size={18} className="text-violet-400" />
            <span>Add Q&A Entry</span>
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Question
              </label>
              <input
                placeholder="What are the class timings?"
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Answer
              </label>
              <textarea
                placeholder="Classes run from 9:00 AM to 3:00 PM."
                value={newAnswer}
                onChange={(e) => setNewAnswer(e.target.value)}
                rows={4}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all"
              />
            </div>
          </div>

          <button
            onClick={addFaq}
            disabled={!newQuestion.trim() || !newAnswer.trim()}
            className="w-full rounded-xl bg-violet-600 py-3 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Add FAQ Entry
          </button>
        </div>

        {/* FAQs List */}
        <div className="lg:col-span-2 space-y-4">
          {faqs.length === 0 && (
            <div className="bg-slate-900 py-16 rounded-3xl border border-slate-800/80 shadow-lg text-center">
              <HelpCircle size={40} className="text-slate-700 mx-auto mb-4 animate-pulse" />
              <h4 className="text-sm font-bold text-white">No FAQ entries yet</h4>
              <p className="text-xs text-slate-400 mt-1">Use the entry form to add questions and answers.</p>
            </div>
          )}

          {faqs.map((faq) => (
            <div 
              key={faq.faq_id} 
              className="bg-slate-900 p-5 rounded-3xl border border-slate-800/80 shadow-sm transition-all hover:shadow-md"
            >
              {editingId === faq.faq_id ? (
                <div className="space-y-4">
                  <div className="space-y-3">
                    <input
                      value={editQuestion}
                      onChange={(e) => setEditQuestion(e.target.value)}
                      placeholder="Question"
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2 text-sm text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
                    />
                    <textarea
                      value={editAnswer}
                      onChange={(e) => setEditAnswer(e.target.value)}
                      rows={3}
                      placeholder="Answer"
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2 text-sm text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => updateFaq(faq.faq_id)} 
                      disabled={!editQuestion.trim() || !editAnswer.trim()}
                      className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-xs font-semibold text-white rounded-xl hover:bg-violet-700 transition-colors cursor-pointer"
                    >
                      <Save size={14} />
                      <span>Save Changes</span>
                    </button>
                    <button 
                      onClick={() => setEditingId(null)}
                      className="flex items-center gap-1.5 px-4 py-2 border border-slate-800 text-xs font-semibold text-slate-400 rounded-xl hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      <X size={14} />
                      <span>Cancel</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex justify-between items-start gap-4">
                  <div className="space-y-2">
                    <h4 className="text-sm font-bold text-white">Q: {faq.question}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">A: {faq.answer}</p>
                  </div>

                  <div className="flex gap-1.5 flex-shrink-0">
                    {isEditor ? (
                      <button
                        onClick={() => {
                          setEditingId(faq.faq_id);
                          setEditQuestion(faq.question);
                          setEditAnswer(faq.answer);
                        }}
                        className="p-2 text-slate-500 hover:text-violet-400 hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
                        title="Edit FAQ"
                      >
                        <Edit3 size={15} />
                      </button>
                    ) : (
                      <span className="p-2 text-slate-700" title="Editing restricted">
                        <Lock size={13} />
                      </span>
                    )}

                    {isAdmin ? (
                      <button
                        onClick={() => deleteFaq(faq.faq_id)}
                        className="p-2 text-slate-500 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
                        title="Delete FAQ"
                      >
                        <Trash2 size={15} />
                      </button>
                    ) : (
                      <span className="p-2 text-slate-750" title="Deleting restricted">
                        <Lock size={13} />
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default FAQs;
