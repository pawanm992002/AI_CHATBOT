import { useState } from 'react';
import { privateAxios } from '../utils/axios';
import { LeadFormConfig, LeadFormField } from '../interfaces';
import {
  Plus,
  Trash2,
  GripVertical,
  Save,
  Loader2,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
  ChevronUp,
  Type,
  Mail,
  Phone,
  AlignLeft,
  List,
  CheckSquare,
  HelpCircle,
} from 'lucide-react';

const FIELD_TYPES: { value: LeadFormField['type']; label: string; icon: typeof Type }[] = [
  { value: 'text', label: 'Text', icon: Type },
  { value: 'email', label: 'Email', icon: Mail },
  { value: 'phone', label: 'Phone', icon: Phone },
  { value: 'textarea', label: 'Text Area', icon: AlignLeft },
  { value: 'select', label: 'Dropdown', icon: List },
  { value: 'checkbox', label: 'Checkbox', icon: CheckSquare },
];

interface LeadFormBuilderProps {
  existingForms: LeadFormConfig[];
  onSaved: () => void;
}

export const LeadFormBuilder = ({ existingForms, onSaved }: LeadFormBuilderProps) => {
  const existing = existingForms.length > 0 ? existingForms[0] : null;

  const [title, setTitle] = useState(existing?.title || 'Leave your details and we\'ll get back to you:');
  const [fields, setFields] = useState<LeadFormField[]>(
    existing?.fields || [
      { field_id: '', label: 'Your Name', type: 'text', required: true, placeholder: 'Your Name', order: 0 },
      { field_id: '', label: 'Your Email', type: 'email', required: true, placeholder: 'Your Email', order: 1 },
      { field_id: '', label: 'Phone', type: 'phone', required: false, placeholder: 'Phone (optional)', order: 2 },
    ]
  );
  const [triggerInstructions, setTriggerInstructions] = useState(
    existing?.trigger_instructions || 'the user is asking about pricing, demo, purchasing, or wants to be contacted'
  );
  const [enabled, setEnabled] = useState(existing?.enabled ?? true);
  const [saving, setSaving] = useState(false);
  const [expandedField, setExpandedField] = useState<number | null>(null);

  const addField = () => {
    const newField: LeadFormField = {
      field_id: '',
      label: '',
      type: 'text',
      required: false,
      placeholder: '',
      order: fields.length,
    };
    setFields([...fields, newField]);
    setExpandedField(fields.length);
  };

  const removeField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index));
    if (expandedField === index) setExpandedField(null);
  };

  const updateField = (index: number, updates: Partial<LeadFormField>) => {
    setFields(fields.map((f, i) => (i === index ? { ...f, ...updates } : f)));
  };

  const moveField = (index: number, direction: 'up' | 'down') => {
    const newFields = [...fields];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newFields.length) return;
    [newFields[index], newFields[targetIndex]] = [newFields[targetIndex], newFields[index]];
    newFields.forEach((f, i) => (f.order = i));
    setFields(newFields);
  };

  const handleSave = async () => {
    if (!title.trim() || fields.length === 0) return;
    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        fields: fields.map((f, i) => ({
          label: f.label,
          type: f.type,
          required: f.required,
          placeholder: f.placeholder || null,
          options: f.type === 'select' ? f.options : null,
          order: i,
        })),
        trigger_instructions: triggerInstructions.trim(),
        enabled,
      };

      if (existing) {
        await privateAxios.put(`/lead-forms/${existing.form_id}`, payload);
      } else {
        await privateAxios.post('/lead-forms', payload);
      }
      onSaved();
    } catch (err) {
      console.error(err);
      alert('Failed to save lead form');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Form Title */}
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
        <h3 className="text-sm font-bold text-white">Form Prompt Text</h3>
        <p className="text-xs text-slate-400">
          This text appears above the form in the widget when it is shown to visitors.
        </p>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-violet-600 focus:outline-none transition-all"
          placeholder="Leave your details and we'll get back to you:"
        />
      </div>

      {/* Enable/Disable Toggle */}
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white">Lead Form Status</h3>
            <p className="text-xs text-slate-400 mt-1">
              {enabled ? 'Form is active and will be shown to visitors when triggered.' : 'Form is disabled and will never be shown.'}
            </p>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            className="cursor-pointer"
          >
            {enabled ? (
              <ToggleRight size={36} className="text-violet-400" />
            ) : (
              <ToggleLeft size={36} className="text-slate-600" />
            )}
          </button>
        </div>
      </div>

      {/* Trigger Instructions */}
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-bold text-white">When to Show This Form</h3>
          <div className="group relative">
            <HelpCircle size={14} className="text-slate-500" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2 bg-slate-800 rounded-lg text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 border border-slate-700">
              The AI chatbot uses these instructions to decide when to show the lead form to visitors. Describe the conditions or triggers.
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-400">
          Describe when the chatbot should show this form to visitors. The AI will use this to decide.
        </p>
        <textarea
          value={triggerInstructions}
          onChange={(e) => setTriggerInstructions(e.target.value)}
          rows={3}
          className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-violet-600 focus:outline-none transition-all resize-none"
          placeholder="the user is asking about pricing, demo, purchasing, or wants to be contacted"
        />
      </div>

      {/* Form Fields */}
      <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white">Form Fields</h3>
          <button
            onClick={addField}
            className="flex items-center gap-1.5 px-3 py-2 bg-violet-600 text-xs font-semibold text-white rounded-xl hover:bg-violet-700 transition-colors cursor-pointer"
          >
            <Plus size={14} />
            Add Field
          </button>
        </div>

        <div className="space-y-3">
          {fields.map((field, index) => (
            <div
              key={index}
              className="bg-slate-950 border border-slate-850 rounded-xl overflow-hidden"
            >
              {/* Field Header */}
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-900/50 transition-colors"
                onClick={() => setExpandedField(expandedField === index ? null : index)}
              >
                <GripVertical size={14} className="text-slate-600" />
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-semibold text-slate-200">
                    {field.label || 'Untitled Field'}
                  </span>
                  <span className="ml-2 text-xxs text-slate-500">
                    {FIELD_TYPES.find(t => t.value === field.type)?.label}
                    {field.required && <span className="text-rose-400 ml-1">*required</span>}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); moveField(index, 'up'); }}
                    disabled={index === 0}
                    className="p-1 text-slate-500 hover:text-slate-300 disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); moveField(index, 'down'); }}
                    disabled={index === fields.length - 1}
                    className="p-1 text-slate-500 hover:text-slate-300 disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronDown size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); removeField(index); }}
                    className="p-1 text-slate-500 hover:text-rose-400 cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Field Details (expanded) */}
              {expandedField === index && (
                <div className="px-4 pb-4 space-y-3 border-t border-slate-850 pt-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                        Label
                      </label>
                      <input
                        value={field.label}
                        onChange={(e) => updateField(index, { label: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                        placeholder="Your Name"
                      />
                    </div>
                    <div>
                      <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                        Placeholder
                      </label>
                      <input
                        value={field.placeholder || ''}
                        onChange={(e) => updateField(index, { placeholder: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none"
                        placeholder="e.g. Enter your name"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                        Field Type
                      </label>
                      <select
                        value={field.type}
                        onChange={(e) => updateField(index, { type: e.target.value as LeadFormField['type'] })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none cursor-pointer"
                      >
                        {FIELD_TYPES.map(t => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                        Required
                      </label>
                      <button
                        onClick={() => updateField(index, { required: !field.required })}
                        className="mt-1 cursor-pointer"
                      >
                        {field.required ? (
                          <ToggleRight size={28} className="text-violet-400" />
                        ) : (
                          <ToggleLeft size={28} className="text-slate-600" />
                        )}
                      </button>
                    </div>
                  </div>

                  {field.type === 'select' && (
                    <div>
                      <label className="text-xxs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                        Options (one per line)
                      </label>
                      <textarea
                        value={(field.options || []).join('\n')}
                        onChange={(e) => updateField(index, { options: e.target.value.split('\n').filter(o => o.trim()) })}
                        rows={3}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-violet-600 focus:outline-none resize-none"
                        placeholder="Option 1&#10;Option 2&#10;Option 3"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {fields.length === 0 && (
            <div className="text-center py-8">
              <p className="text-xs text-slate-500">No fields added yet. Click "Add Field" to start building your form.</p>
            </div>
          )}
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving || !title.trim() || fields.length === 0}
          className="flex items-center gap-2 px-6 py-3 bg-violet-600 text-sm font-semibold text-white rounded-xl shadow-sm hover:bg-violet-700 transition-colors disabled:opacity-50 cursor-pointer"
        >
          {saving ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save size={16} />
              Save Lead Form
            </>
          )}
        </button>
      </div>
    </div>
  );
};
