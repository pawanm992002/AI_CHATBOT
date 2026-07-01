import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { VisitorProfile, ProfileRule } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import {
  Plus,
  Trash2,
  Save,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Users,
  Palette,
  FileText,
  HelpCircle,
} from 'lucide-react';

interface ProfileFormState {
  name: string;
  description: string;
  color: string;
  rules: ProfileRuleInput[];
  llm_criteria: string;
  enabled: boolean;
}

interface ProfileRuleInput {
  type: ProfileRule['type'];
  priority: number;
  pattern?: string;
  field_key?: string;
  count?: number;
  keywords?: string;
  sources?: string;
}

const DEFAULT_FORM: ProfileFormState = {
  name: '',
  description: '',
  color: '#6366f1',
  rules: [],
  llm_criteria: '',
  enabled: true,
};

const RULE_TYPE_LABELS: Record<ProfileRule['type'], string> = {
  page_visited: 'Page Visited',
  lead_form_field: 'Lead Form Field',
  message_count_gte: 'Message Count >=',
  keyword_match: 'Keyword Match',
  utm_source: 'UTM Source',
};

const VisitorProfiles = () => {
  const [profiles, setProfiles] = useState<VisitorProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ProfileFormState>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const selectedProfile = selectedId ? profiles.find(p => p.profile_id === selectedId) ?? null : null;

  const fetchProfiles = async () => {
    try {
      const res = await privateAxios.get('/dashboard/visitor-profiles');
      setProfiles(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchProfiles();
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    if (selectedId === 'new') {
      setForm(DEFAULT_FORM);
    } else if (selectedProfile) {
      setForm({
        name: selectedProfile.name,
        description: selectedProfile.description,
        color: selectedProfile.color,
        rules: selectedProfile.rules.map(r => ({
          ...r,
          keywords: r.keywords ? r.keywords.join('\n') : '',
          sources: r.sources ? r.sources.join('\n') : '',
        })),
        llm_criteria: selectedProfile.llm_criteria || '',
        enabled: selectedProfile.enabled,
      });
    }
  }, [selectedId, selectedProfile]);

  const addRule = () => {
    setForm(f => ({
      ...f,
      rules: [...f.rules, { type: 'page_visited', priority: 0, pattern: '' }],
    }));
  };

  const updateRule = (index: number, updates: Partial<ProfileRuleInput>) => {
    setForm(f => ({
      ...f,
      rules: f.rules.map((r, i) => (i === index ? { ...r, ...updates } : r)),
    }));
  };

  const removeRule = (index: number) => {
    setForm(f => ({
      ...f,
      rules: f.rules.filter((_, i) => i !== index),
    }));
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        color: form.color,
        rules: form.rules.map(r => {
          const base: any = { type: r.type, priority: r.priority };
          if (r.type === 'page_visited') base.pattern = r.pattern || '';
          else if (r.type === 'lead_form_field') { base.field_key = r.field_key || ''; base.pattern = r.pattern || ''; }
          else if (r.type === 'message_count_gte') base.count = r.count || 1;
          else if (r.type === 'keyword_match') base.keywords = (r.keywords || '').split('\n').filter(Boolean);
          else if (r.type === 'utm_source') base.sources = (r.sources || '').split('\n').filter(Boolean);
          return base;
        }),
        llm_criteria: form.llm_criteria.trim() || null,
        enabled: form.enabled,
      };

      if (selectedId && selectedId !== 'new') {
        await privateAxios.put(`/dashboard/visitor-profiles/${selectedId}`, payload);
      } else {
        await privateAxios.post('/dashboard/visitor-profiles', payload);
      }
      await fetchProfiles();
      setSelectedId(null);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (profile: VisitorProfile) => {
    setTogglingId(profile.profile_id);
    try {
      await privateAxios.put(`/dashboard/visitor-profiles/${profile.profile_id}`, { enabled: !profile.enabled });
      await fetchProfiles();
    } catch (err) {
      console.error(err);
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (profile: VisitorProfile) => {
    if (!window.confirm(`Delete profile "${profile.name}"?`)) return;
    try {
      await privateAxios.delete(`/dashboard/visitor-profiles/${profile.profile_id}`);
      if (selectedId === profile.profile_id) setSelectedId(null);
      await fetchProfiles();
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading visitor profiles..." />;
  }

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Visitor Profiles</h2>
        <p className="text-slate-400 text-sm mt-1">
          Define visitor categories for classification. Rules are evaluated first; LLM criteria used as fallback.
        </p>
      </div>

      <div className="flex gap-6 min-h-[600px]">
        {/* Sidebar */}
        <div className="w-72 flex-shrink-0 bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-800">
            <button
              onClick={() => setSelectedId('new')}
              className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl transition-colors cursor-pointer ${
                selectedId === 'new' ? 'bg-violet-500 text-white shadow-sm' : 'bg-violet-600 text-white hover:bg-violet-700'
              }`}
            >
              <Plus size={16} />
              New Profile
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {profiles.length === 0 ? (
              <div className="py-12 text-center">
                <Users size={32} className="text-slate-700 mx-auto mb-3" />
                <p className="text-xs text-slate-500">No profiles yet</p>
                <p className="text-xxs text-slate-600 mt-1">Click "New Profile" to create one</p>
              </div>
            ) : (
              profiles.map(profile => {
                const isSelected = selectedId === profile.profile_id;
                return (
                  <div
                    key={profile.profile_id}
                    onClick={() => setSelectedId(profile.profile_id)}
                    className={`group relative p-3 rounded-xl cursor-pointer transition-all ${
                      isSelected ? 'bg-violet-600/10 border border-violet-600/30' : 'hover:bg-slate-800/60 border border-transparent'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: profile.color }} />
                          <p className={`text-sm font-semibold truncate ${isSelected ? 'text-violet-300' : 'text-slate-200'}`}>
                            {profile.name}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 mt-1 ml-4">
                          <span className="text-xxs text-slate-500">
                            {profile.rules.length} rule{profile.rules.length !== 1 ? 's' : ''}
                            {profile.llm_criteria ? ' + LLM' : ''}
                          </span>
                          <span className={`w-1.5 h-1.5 rounded-full ${profile.enabled ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                        </div>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleToggle(profile); }}
                          disabled={togglingId === profile.profile_id}
                          className="p-1 cursor-pointer disabled:opacity-50"
                        >
                          {profile.enabled ? <ToggleRight size={18} className="text-emerald-400" /> : <ToggleLeft size={18} className="text-slate-600" />}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(profile); }}
                          className="p-1 text-slate-500 hover:text-rose-400 cursor-pointer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 min-w-0 space-y-6">
          {selectedId ? (
            <>
              {/* Name & Description */}
              <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
                <h3 className="text-sm font-bold text-white">Profile Details</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Name</label>
                    <input
                      value={form.name}
                      onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-violet-600 focus:outline-none"
                      placeholder="Ready to buy"
                    />
                  </div>
                  <div>
                    <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                      <span className="flex items-center gap-1.5">
                        <Palette size={12} />
                        Color
                      </span>
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={form.color}
                        onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                        className="w-10 h-10 rounded-lg cursor-pointer bg-slate-950 border border-slate-800"
                      />
                      <span className="text-xs text-slate-400 font-mono">{form.color}</span>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Description</label>
                  <input
                    value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-violet-600 focus:outline-none"
                    placeholder="Visitors who are likely to purchase"
                  />
                </div>
              </div>

              {/* Enabled Toggle */}
              <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-white">Profile Status</h3>
                    <p className="text-xs text-slate-400 mt-1">
                      {form.enabled ? 'Active and used for visitor classification.' : 'Disabled and will not be assigned.'}
                    </p>
                  </div>
                  <button onClick={() => setForm(f => ({ ...f, enabled: !f.enabled }))} className="cursor-pointer">
                    {form.enabled ? <ToggleRight size={36} className="text-violet-400" /> : <ToggleLeft size={36} className="text-slate-600" />}
                  </button>
                </div>
              </div>

              {/* Rules */}
              <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-white">Rules (first match wins)</h3>
                  <button onClick={addRule} className="flex items-center gap-1.5 px-3 py-2 bg-violet-600 text-xs font-semibold text-white rounded-xl hover:bg-violet-700 transition-colors cursor-pointer">
                    <Plus size={14} />
                    Add Rule
                  </button>
                </div>
                {form.rules.map((rule, index) => (
                  <div key={index} className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-400">Rule #{index + 1}</span>
                        <span className="text-xxs bg-slate-800 px-2 py-0.5 rounded-full text-slate-400">
                          Priority: {rule.priority}
                        </span>
                      </div>
                      <button onClick={() => removeRule(index)} className="p-1 text-slate-500 hover:text-rose-400 cursor-pointer">
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <div className="grid grid-cols-4 gap-3">
                      <div className="col-span-2">
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Type</label>
                        <select
                          value={rule.type}
                          onChange={e => updateRule(index, { type: e.target.value as ProfileRule['type'] })}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none cursor-pointer"
                        >
                          {Object.entries(RULE_TYPE_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Priority</label>
                        <input
                          type="number"
                          min={0}
                          value={rule.priority}
                          onChange={e => updateRule(index, { priority: parseInt(e.target.value) || 0 })}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                        />
                      </div>
                    </div>

                    {rule.type === 'page_visited' && (
                      <div>
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">URL Pattern (supports wildcards)</label>
                        <input
                          value={rule.pattern || ''}
                          onChange={e => updateRule(index, { pattern: e.target.value })}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                          placeholder="/pricing*"
                        />
                      </div>
                    )}
                    {rule.type === 'lead_form_field' && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Field Key</label>
                          <input
                            value={rule.field_key || ''}
                            onChange={e => updateRule(index, { field_key: e.target.value })}
                            className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                            placeholder="budget"
                          />
                        </div>
                        <div>
                          <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Value Pattern</label>
                          <input
                            value={rule.pattern || ''}
                            onChange={e => updateRule(index, { pattern: e.target.value })}
                            className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                            placeholder="enterprise"
                          />
                        </div>
                      </div>
                    )}
                    {rule.type === 'message_count_gte' && (
                      <div>
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Minimum Message Count</label>
                        <input
                          type="number"
                          min={1}
                          value={rule.count || 1}
                          onChange={e => updateRule(index, { count: parseInt(e.target.value) || 1 })}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                        />
                      </div>
                    )}
                    {rule.type === 'keyword_match' && (
                      <div>
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                          Keywords (one per line)
                          <span className="text-slate-600 font-normal lowercase ml-1">regex supported</span>
                        </label>
                        <textarea
                          value={rule.keywords || ''}
                          onChange={e => updateRule(index, { keywords: e.target.value })}
                          rows={3}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none resize-none"
                          placeholder="pricing&#10;cost&#10;how much"
                        />
                      </div>
                    )}
                    {rule.type === 'utm_source' && (
                      <div>
                        <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">UTM Sources (one per line)</label>
                        <textarea
                          value={rule.sources || ''}
                          onChange={e => updateRule(index, { sources: e.target.value })}
                          rows={3}
                          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none resize-none"
                          placeholder="google&#10;facebook&#10;linkedin"
                        />
                      </div>
                    )}
                  </div>
                ))}
                {form.rules.length === 0 && (
                  <p className="text-xs text-slate-500 text-center py-4">No rules defined. Add rules or use LLM criteria below.</p>
                )}
              </div>

              {/* LLM Criteria */}
              <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-white">LLM Criteria (fallback)</h3>
                  <div className="group relative">
                    <HelpCircle size={14} className="text-slate-500" />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-2 bg-slate-800 rounded-lg text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 border border-slate-700">
                      Free-text description used for LLM-based fallback classification when no rules match. Describe the visitor behavior that fits this profile.
                    </div>
                  </div>
                </div>
                <p className="text-xs text-slate-400">
                  If no rules match, the LLM will classify the visitor based on this description.
                </p>
                <textarea
                  value={form.llm_criteria}
                  onChange={e => setForm(f => ({ ...f, llm_criteria: e.target.value }))}
                  rows={4}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-violet-600 focus:outline-none transition-all resize-none"
                  placeholder="Visitors who ask about pricing, request demos, or inquire about enterprise plans. They tend to use words like 'cost', 'quote', 'subscription', 'plan'."
                />
              </div>

              {/* Save */}
              <div className="flex justify-end">
                <button
                  onClick={handleSave}
                  disabled={saving || !form.name.trim()}
                  className="flex items-center gap-2 px-6 py-3 bg-violet-600 text-sm font-semibold text-white rounded-xl shadow-sm hover:bg-violet-700 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {saving ? (
                    <><Loader2 size={16} className="animate-spin" /> Saving...</>
                  ) : (
                    <><Save size={16} /> {selectedId === 'new' ? 'Create Profile' : 'Update Profile'}</>
                  )}
                </button>
              </div>
            </>
          ) : (
            <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg h-full flex items-center justify-center">
              <div className="text-center px-6">
                <FileText size={48} className="text-slate-700 mx-auto mb-4" />
                <h3 className="text-base font-bold text-white">Select a profile to edit</h3>
                <p className="text-xs text-slate-500 mt-2 max-w-xs mx-auto">
                  Choose a profile from the sidebar to edit it, or click "New Profile" to create one.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VisitorProfiles;