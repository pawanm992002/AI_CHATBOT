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
                  {selectedProvider === 'openai' && (
                    <>
                      <optgroup label="GPT-5.5 (Frontier)">
                        <option value="gpt-5.5">GPT-5.5 — $5.00/$30.00 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="GPT-5.4 (Mainstream)">
                        <option value="gpt-5.4">GPT-5.4 — $2.50/$15.00 per 1M tokens</option>
                        <option value="gpt-5.4-mini">GPT-5.4 Mini — $0.75/$4.50 per 1M tokens</option>
                        <option value="gpt-5.4-nano">GPT-5.4 Nano — $0.20/$1.25 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="GPT-5 (Legacy Flagship)">
                        <option value="gpt-5">GPT-5 — $1.25/$10.00 per 1M tokens</option>
                        <option value="gpt-5-mini">GPT-5 Mini — $0.25/$2.00 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="GPT-4.1 (Production)">
                        <option value="gpt-4.1">GPT-4.1 — $2.00/$8.00 per 1M tokens</option>
                        <option value="gpt-4.1-mini">GPT-4.1 Mini — $0.40/$1.60 per 1M tokens</option>
                        <option value="gpt-4.1-nano">GPT-4.1 Nano — $0.10/$0.40 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="GPT-4o (Legacy)">
                        <option value="gpt-4o">GPT-4o — $2.50/$10.00 per 1M tokens</option>
                        <option value="gpt-4o-mini">GPT-4o Mini — $0.15/$0.60 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Reasoning (o-Series)">
                        <option value="o3">o3 — $2.00/$8.00 per 1M tokens</option>
                        <option value="o4-mini">o4-mini — $1.10/$4.40 per 1M tokens</option>
                        <option value="o3-pro">o3-Pro — $20.00/$80.00 per 1M tokens</option>
                      </optgroup>
                    </>
                  )}
                  {selectedProvider === 'groq' && (
                    <>
                      <optgroup label="Llama (Meta)">
                        <option value="llama-3.3-70b-versatile">Llama 3.3 70B — $0.59/$0.79 per 1M tokens</option>
                        <option value="llama-4-scout-17b-16e-instruct">Llama 4 Scout 17B — $0.11/$0.34 per 1M tokens</option>
                        <option value="llama-4-maverick-17b-128e-instruct">Llama 4 Maverick 17B — $0.20/$0.60 per 1M tokens</option>
                        <option value="llama-3.1-8b-instant">Llama 3.1 8B Instant — $0.05/$0.08 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Qwen (Alibaba)">
                        <option value="qwen/qwen3-32b">Qwen3 32B — $0.29/$0.59 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="GPT-OSS (OpenAI Open-Source)">
                        <option value="openai/gpt-oss-120b">GPT-OSS 120B — $0.15/$0.60 per 1M tokens</option>
                        <option value="openai/gpt-oss-20b">GPT-OSS 20B — $0.075/$0.30 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="DeepSeek">
                        <option value="deepseek-r2">DeepSeek R2 (Reasoning) — $0.70/$2.70 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Moonshot">
                        <option value="moonshotai/kimi-k2-instruct-0905">Kimi K2 — $1.00/$3.00 per 1M tokens</option>
                      </optgroup>
                    </>
                  )}
                  {selectedProvider === 'openrouter' && (
                    <>
                      <optgroup label="DeepSeek">
                        <option value="deepseek/deepseek-chat-v3-0324">DeepSeek V3 — $0.27/$1.10 per 1M tokens</option>
                        <option value="deepseek/deepseek-r1">DeepSeek R1 (Reasoning) — $0.55/$2.19 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Anthropic">
                        <option value="anthropic/claude-sonnet-4">Claude Sonnet 4 — $3.00/$15.00 per 1M tokens</option>
                        <option value="anthropic/claude-haiku-3.5">Claude 3.5 Haiku — $0.80/$4.00 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Google">
                        <option value="google/gemini-2.5-flash">Gemini 2.5 Flash — $0.15/$0.60 per 1M tokens</option>
                        <option value="google/gemini-2.5-pro">Gemini 2.5 Pro — $1.25/$10.00 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Meta">
                        <option value="meta-llama/llama-4-maverick">Llama 4 Maverick — $0.20/$0.60 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Qwen">
                        <option value="qwen/qwen3-235b-a22b">Qwen3 235B — $0.60/$3.60 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="Mistral">
                        <option value="mistralai/mistral-large-2411">Mistral Large — $2.00/$6.00 per 1M tokens</option>
                      </optgroup>
                      <optgroup label="xAI">
                        <option value="x-ai/grok-3-mini">Grok 3 Mini — $0.30/$0.50 per 1M tokens</option>
                      </optgroup>
                    </>
                  )}
                  {selectedProvider && selectedProvider !== 'openai' && selectedProvider !== 'groq' && selectedProvider !== 'openrouter' && models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} — ${m.input_price}/M in, ${m.output_price}/M out
                    </option>
                  ))}
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
