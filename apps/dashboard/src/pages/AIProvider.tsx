import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { useStore, hasAccess } from '../store';
import { LoadingSpinner } from '@chatbot/shared';
import { useRbacError } from '../hooks/useRbacError';
import { Brain, Lock, Check, Zap } from 'lucide-react';

const AIProvider = () => {
  const { state } = useStore();
  const { rbacError, triggerRbacError } = useRbacError();
  const isEditor = hasAccess(state.role, 'write');

  const [me, setMe] = useState<any>(null);
  const [providers, setProviders] = useState<string[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const currentProvider = me?.ai?.provider || 'openai';
  const currentModel = me?.ai?.model || 'gpt-4o-mini';

  const fetchMe = async () => {
    try {
      const res = await privateAxios.get('/tenants/me');
      setMe(res.data);
      const ai = res.data.ai || {};
      setSelectedProvider(ai.provider || 'openai');
      setSelectedModel(ai.model || 'gpt-4o-mini');
    } catch (err) {
      console.error(err);
    }
  };

  const fetchProviders = async () => {
    try {
      const res = await privateAxios.get('/providers');
      setProviders(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchModels = async (provider: string) => {
    if (!provider) return;
    try {
      const res = await privateAxios.get(`/providers/${provider}/models`);
      setModels(res.data);
    } catch (err) {
      console.error(err);
      setModels([]);
    }
  };

  useEffect(() => {
    fetchMe();
    fetchProviders();
  }, []);

  useEffect(() => {
    if (selectedProvider) {
      fetchModels(selectedProvider);
    }
  }, [selectedProvider]);

  const handleSave = async () => {
    if (!isEditor) {
      triggerRbacError("You do not have Editor permissions to update AI settings.");
      return;
    }
    setSaving(true);
    setSaved(false);
    try {
      await privateAxios.put('/tenants/ai', { provider: selectedProvider, model: selectedModel });
      setMe((prev: any) => prev ? { ...prev, ai: { provider: selectedProvider, model: selectedModel } } : null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to save AI config');
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = selectedProvider !== currentProvider || selectedModel !== currentModel;

  if (!me) return <LoadingSpinner message="Loading AI settings..." />;

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">AI Provider</h2>
        <p className="text-slate-400 text-sm mt-1">
          Choose which LLM provider and model powers your chatbot responses.
        </p>
      </div>

      {rbacError && (
        <div className="flex items-center gap-3 bg-rose-950/20 border border-rose-900/50 p-4 rounded-2xl text-xs text-rose-350 animate-slideUp">
          <Lock size={16} className="flex-shrink-0" />
          <span>{rbacError}</span>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-6">
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Zap size={18} className="text-violet-400" />
              <span>Current Configuration</span>
            </h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between rounded-xl bg-slate-950 px-4 py-3">
                <span className="text-xs text-slate-400">Provider</span>
                <span className="text-xs font-semibold text-white capitalize">{currentProvider}</span>
              </div>
              <div className="flex items-center justify-between rounded-xl bg-slate-950 px-4 py-3">
                <span className="text-xs text-slate-400">Model</span>
                <span className="text-xs font-semibold text-white">{currentModel}</span>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Brain size={18} className="text-emerald-400" />
              <span>Change Provider</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Select a different provider or model to change how your chatbot generates responses.
            </p>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider">Provider</label>
                <select
                  value={selectedProvider}
                  onChange={(e) => {
                    setSelectedProvider(e.target.value);
                    setSelectedModel('');
                  }}
                  disabled={!isEditor}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-slate-200 focus:border-violet-600 focus:outline-none transition-all cursor-pointer disabled:opacity-50"
                >
                  {providers.map((p) => (
                    <option key={p} value={p.toLowerCase()}>{p}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider">Model</label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={!isEditor || !selectedProvider}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-slate-200 focus:border-violet-600 focus:outline-none transition-all cursor-pointer disabled:opacity-50"
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} — ${m.input_price}/M in, ${m.output_price}/M out
                    </option>
                  ))}
                  {models.length === 0 && selectedProvider && (
                    <option value="" disabled>No models available</option>
                  )}
                </select>
              </div>
            </div>

            <button
              onClick={handleSave}
              disabled={saving || !isEditor || !selectedProvider || !selectedModel || !hasChanges}
              className="w-full rounded-xl bg-emerald-600 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
            >
              {saving ? (
                'Saving...'
              ) : saved ? (
                <>
                  <Check size={14} />
                  Saved
                </>
              ) : (
                'Save AI Config'
              )}
            </button>
            {!isEditor && <Lock size={12} className="text-slate-500" />}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Zap size={18} className="text-amber-400" />
              <span>How It Works</span>
            </h3>
            <div className="space-y-3 text-xs text-slate-400 leading-relaxed">
              <p>
                The AI provider determines how your chatbot generates responses. Each provider offers different models with varying capabilities and pricing.
              </p>
              <div className="space-y-2">
                <div className="rounded-xl bg-slate-950 px-4 py-3">
                  <span className="font-semibold text-white">OpenAI</span>
                  <span className="text-slate-500"> — Industry-leading models like GPT-4o and GPT-4o-mini. Best overall quality.</span>
                </div>
                <div className="rounded-xl bg-slate-950 px-4 py-3">
                  <span className="font-semibold text-white">Groq</span>
                  <span className="text-slate-500"> — Ultra-fast inference on open-source models. Great for speed-sensitive deployments.</span>
                </div>
                <div className="rounded-xl bg-slate-950 px-4 py-3">
                  <span className="font-semibold text-white">OpenRouter</span>
                  <span className="text-slate-500"> — Access to Claude, Gemini, Llama, and more. Best for trying different providers.</span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Brain size={18} className="text-sky-400" />
              <span>Affected Features</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Changing the provider affects all LLM-powered features:
            </p>
            <div className="space-y-1.5">
              {[
                'Chat responses',
                'Query classification',
                'Query rewriting',
                'Business description generation',
                'Suggested questions',
                'Lead conversation summarization',
              ].map((feature) => (
                <div key={feature} className="flex items-center gap-2 text-xs text-slate-300">
                  <Check size={12} className="text-emerald-400" />
                  <span>{feature}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIProvider;
