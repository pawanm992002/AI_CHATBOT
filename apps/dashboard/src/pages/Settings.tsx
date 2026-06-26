import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { useStore, hasAccess } from '../store';
import { LoadingSpinner } from '@chatbot/shared';
import { useRbacError } from '../hooks/useRbacError';
import { Copy, Check, RotateCw, Key, HelpCircle, Code, Plus, Trash2, Lock, ExternalLink, Monitor } from 'lucide-react';

const Settings = () => {
  const { state } = useStore();
  const [me, setMe] = useState<any>(null);
  const [manualQuestions, setManualQuestions] = useState<string[]>([]);
  const [autoQuestions, setAutoQuestions] = useState<string[]>([]);
  const [newQuestion, setNewQuestion] = useState('');
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const { rbacError, triggerRbacError } = useRbacError();
  const [showSources, setShowSources] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  const isEditor = hasAccess(state.role, 'write');
  const isAdmin = hasAccess(state.role, 'delete');

  const fetchMe = async () => {
    try {
      const res = await privateAxios.get('/tenants/me');
      setMe(res.data);
      setManualQuestions(res.data.suggested_questions_manual || []);
      setAutoQuestions(res.data.suggested_questions_auto || []);
      setShowSources(res.data.show_sources !== false);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchMe();
  }, []);

  const rotateKey = async () => {
    if (!isAdmin) {
      triggerRbacError("You do not have Administrator permissions to rotate the API key.");
      return;
    }
    if (!window.confirm('Are you sure? This will invalidate your current API key and break existing widget installations.')) return;
    try {
      const res = await privateAxios.post('/tenants/rotate_key');
      setMe((prev: any) => prev ? { ...prev, api_key: res.data.api_key } : null);
    } catch (err) {
      console.error(err);
    }
  };

  const toggleSources = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to update widget settings.");
      return;
    }
    setSavingSettings(true);
    try {
      const newValue = !showSources;
      await privateAxios.put('/tenants/widget-settings', null, { params: { show_sources: newValue } });
      setShowSources(newValue);
      setMe((prev: any) => prev ? { ...prev, show_sources: newValue } : null);
    } catch (err) {
      console.error(err);
    } finally {
      setSavingSettings(false);
    }
  };

  const addQuestion = () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to add suggested questions.");
      return;
    }
    const q = newQuestion.trim();
    if (!q || manualQuestions.includes(q)) return;
    setManualQuestions([...manualQuestions, q]);
    setNewQuestion('');
  };

  const removeQuestion = (index: number) => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to remove suggested questions.");
      return;
    }
    setManualQuestions(manualQuestions.filter((_, i) => i !== index));
  };

  const saveQuestions = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to save suggested questions.");
      return;
    }
    setSaving(true);
    try {
      await privateAxios.put('/tenants/suggested-questions', { questions: manualQuestions });
      alert('Suggested questions saved!');
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1700);
  };

  if (!me) {
    return <LoadingSpinner message="Loading settings..." />;
  }

  const widgetUrl = window.location.origin;
  const snippet = `<script src="${widgetUrl}/static/widget.js" data-api-key="${me.api_key}"></script>`;
  const testUrl = `${widgetUrl}/tenants/test`;

  const openTestPage = () => {
    window.open(testUrl, '_blank', 'noopener,noreferrer');
  };

  const copyTestUrl = () => {
    navigator.clipboard.writeText(testUrl).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1700);
  };

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Console Settings</h2>
        <p className="text-slate-400 text-sm mt-1">Configure widget connection API keys and suggestion presets.</p>
      </div>

      {/* RBAC Error Banner */}
      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/20 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Left Side: Keys and connection */}
        <div className="space-y-6">
          {/* API Key Rotation */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Key size={18} className="text-violet-400" />
              <span>Widget Connection API Key</span>
            </h3>
            
            <div className="flex flex-col sm:flex-row gap-3 items-stretch">
              <div className="flex-1 rounded-xl bg-slate-950 border border-slate-850 px-4 py-3 font-mono text-xs text-slate-300 truncate select-all flex items-center">
                {me.api_key}
              </div>
              <button 
                onClick={rotateKey}
                className="flex items-center justify-center gap-1.5 px-4 py-3 bg-rose-950/20 text-xs font-semibold text-rose-405 hover:bg-rose-950/40 rounded-xl transition-colors cursor-pointer border border-rose-900/30"
              >
                {!isAdmin && <Lock size={13} />}
                <RotateCw size={14} />
                <span>Rotate Key</span>
              </button>
            </div>
            <p className="text-xxs text-slate-500 font-semibold leading-relaxed">
              Rotating your key immediately revokes access for older widget integrations. Use with caution.
            </p>
          </div>

          {/* Installation snippet */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Code size={18} className="text-indigo-400" />
              <span>Embed Installation Snippet</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Add this lightweight JavaScript hook right before the closing <code>&lt;/body&gt;</code> tag on your pages:
            </p>

            <div className="relative rounded-2xl bg-slate-950 p-5 text-indigo-300 font-mono text-xs leading-relaxed select-all border border-slate-850">
              <button
                onClick={() => copyToClipboard(snippet)}
                className="absolute top-3 right-3 p-2 bg-slate-900 hover:bg-slate-800 text-indigo-300 rounded-lg transition-colors cursor-pointer border border-slate-800"
                title="Copy snippet"
              >
                {copied ? <Check size={14} className="text-teal-400" /> : <Copy size={14} />}
              </button>
              <pre className="overflow-x-auto whitespace-pre-wrap">{snippet}</pre>
            </div>
          </div>

          {/* Test Chatbot */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Monitor size={18} className="text-teal-400" />
              <span>Test Chatbot</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Try your chatbot instantly without installing it on your website. Opens in a new tab with your API key pre-configured.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={openTestPage}
                className="flex items-center justify-center gap-2 px-5 py-3 bg-teal-600 text-sm font-semibold text-white rounded-xl shadow-sm hover:bg-teal-700 transition-colors cursor-pointer"
              >
                <Monitor size={16} />
                <span>Open Test Page</span>
              </button>
              <button
                onClick={copyTestUrl}
                className="flex items-center justify-center gap-2 px-5 py-3 bg-slate-800 text-sm font-semibold text-slate-200 rounded-xl border border-slate-700 hover:bg-slate-700 transition-colors cursor-pointer"
              >
                {copied ? <Check size={14} className="text-teal-400" /> : <ExternalLink size={14} />}
                <span>{copied ? 'Copied!' : 'Copy Test URL'}</span>
              </button>
            </div>
            <p className="text-xxs text-slate-500 font-semibold leading-relaxed truncate" title={testUrl}>
              {testUrl}
            </p>
          </div>

          {/* Widget Settings */}
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Monitor size={18} className="text-violet-400" />
              <span>Widget Configuration</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Customize the behavior of the chatbot widget on your website.
            </p>
            <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-850">
              <div>
                <p className="text-xs font-semibold text-slate-200">Show Reference Sources</p>
                <p className="text-xxs text-slate-500 mt-0.5">Display links to crawled pages used to generate answers.</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleSources}
                  disabled={savingSettings || !isEditor}
                  className={`${
                    showSources ? 'bg-violet-600' : 'bg-slate-700'
                  } relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 cursor-pointer`}
                >
                  <span
                    className={`${
                      showSources ? 'translate-x-6' : 'translate-x-1'
                    } inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                  />
                </button>
                {!isEditor && <Lock size={12} className="text-slate-500" />}
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Suggested Questions */}
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-6 h-fit">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <HelpCircle size={18} className="text-violet-400" />
            <span>Suggested Starter Questions</span>
          </h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Configure preset chips shown to visitors opening empty chat sessions.
          </p>

          {/* Auto suggestions */}
          {autoQuestions.length > 0 && (
            <div className="space-y-2.5">
              <span className="text-xxs font-bold text-slate-500 uppercase tracking-wider block">
                Auto-generated from content
              </span>
              <div className="flex flex-wrap gap-1.5">
                {autoQuestions.map((q, idx) => (
                  <span 
                    key={idx} 
                    className="inline-flex rounded-lg bg-slate-950 px-2.5 py-1 text-xs text-slate-300 font-semibold border border-slate-850"
                  >
                    {q}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Manual questions manager */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <span className="text-xxs font-bold text-slate-500 uppercase tracking-wider block">
              Manual Custom Presets
            </span>

            <div className="flex gap-2">
              <input
                placeholder="Type suggested question preset..."
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addQuestion()}
                className="flex-1 rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
              />
              <button 
                onClick={addQuestion}
                className="flex items-center gap-1 px-4 py-2.5 bg-violet-600 text-xs font-semibold text-white rounded-xl shadow-sm hover:bg-violet-700 transition-colors cursor-pointer"
              >
                <Plus size={14} />
                <span>Add</span>
              </button>
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto">
              {manualQuestions.map((q, idx) => (
                <div 
                  key={idx} 
                  className="flex items-center justify-between gap-3 bg-slate-950 p-3 rounded-xl border border-slate-850"
                >
                  <span className="text-xs text-slate-300 font-semibold">{q}</span>
                  <button 
                    onClick={() => removeQuestion(idx)}
                    className="p-1 text-slate-500 hover:text-rose-400 rounded-lg transition-colors cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {manualQuestions.length === 0 && (
                <p className="text-xs text-slate-500 italic">No manual presets added yet.</p>
              )}
            </div>
          </div>

          <button
            onClick={saveQuestions}
            disabled={saving}
            className="w-full rounded-xl bg-violet-600 py-3 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {saving ? 'Saving changes...' : 'Save Presets'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;