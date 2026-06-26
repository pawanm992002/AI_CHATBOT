import { useState } from 'react';
import { Palette } from '../utils/theme';
import { LeadFormConfig, LeadFormFieldConfig } from '../api';

interface EnquiryFormProps {
  accent: string;
  palette: Palette;
  formConfig: LeadFormConfig | null;
  onSubmit: (data: { custom_fields: Record<string, string>; form_id?: string }) => void;
}

// Default fields when no form config exists (backward compatible)
const DEFAULT_FIELDS: LeadFormFieldConfig[] = [
  { field_id: 'name', label: 'Your Name', type: 'text', required: true, placeholder: 'Your Name *', order: 0 },
  { field_id: 'email', label: 'Your Email', type: 'email', required: true, placeholder: 'Your Email *', order: 1 },
  { field_id: 'phone', label: 'Phone', type: 'phone', required: false, placeholder: 'Phone (optional)', order: 2 },
];

export function EnquiryForm({ accent, palette, formConfig, onSubmit }: EnquiryFormProps) {
  const fields = formConfig?.fields?.length ? formConfig.fields : DEFAULT_FIELDS;
  const title = formConfig?.title || "Leave your details and we'll get back to you:";
  const formId = formConfig?.form_id;

  const [formData, setFormData] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    fields.forEach(f => { initial[f.field_id] = ''; });
    return initial;
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    fields.forEach(f => {
      const val = (formData[f.field_id] || '').trim();
      if (f.required && !val) {
        newErrors[f.field_id] = `${f.label} is required`;
      }
      if (val && f.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        newErrors[f.field_id] = 'Invalid email address';
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleFormSubmit = () => {
    if (!validate()) return;
    const trimmed: Record<string, string> = {};
    fields.forEach(f => {
      trimmed[f.field_id] = (formData[f.field_id] || '').trim();
    });
    onSubmit({ custom_fields: trimmed, form_id: formId });
  };

  const isFormValid = fields
    .filter(f => f.required)
    .every(f => (formData[f.field_id] || '').trim());

  const inputClass = "w-full px-3 py-2.25 mb-1.5 rounded-lg border outline-none text-[13px] box-border transition-colors duration-150";

  const renderField = (field: LeadFormFieldConfig) => {
    const value = formData[field.field_id] || '';
    const error = errors[field.field_id];
    const baseStyle = {
      borderColor: error ? '#ef4444' : palette.inputBorder,
      backgroundColor: palette.inputBg,
      color: palette.inputText,
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      e.currentTarget.style.borderColor = error ? '#ef4444' : accent;
    };
    const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      e.currentTarget.style.borderColor = error ? '#ef4444' : palette.inputBorder;
    };

    const placeholder = field.placeholder || field.label + (field.required ? ' *' : '');

    switch (field.type) {
      case 'textarea':
        return (
          <div key={field.field_id} className="mb-1.5">
            <textarea
              placeholder={placeholder}
              value={value}
              onChange={(e) => setFormData(prev => ({ ...prev, [field.field_id]: e.target.value }))}
              className="w-full px-3 py-2.25 rounded-lg border outline-none text-[13px] box-border transition-colors duration-150 resize-none"
              rows={3}
              style={baseStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
            {error && <p className="text-[11px] text-red-400 mt-0.5 mb-0">{error}</p>}
          </div>
        );

      case 'select':
        return (
          <div key={field.field_id} className="mb-1.5">
            <select
              value={value}
              onChange={(e) => setFormData(prev => ({ ...prev, [field.field_id]: e.target.value }))}
              className="w-full px-3 py-2.25 rounded-lg border outline-none text-[13px] box-border transition-colors duration-150 cursor-pointer"
              style={baseStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            >
              <option value="">{placeholder}</option>
              {(field.options || []).map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
            {error && <p className="text-[11px] text-red-400 mt-0.5 mb-0">{error}</p>}
          </div>
        );

      case 'checkbox':
        return (
          <div key={field.field_id} className="mb-1.5 flex items-center gap-2">
            <input
              type="checkbox"
              checked={value === 'true'}
              onChange={(e) => setFormData(prev => ({ ...prev, [field.field_id]: e.target.checked ? 'true' : '' }))}
              className="w-4 h-4 rounded cursor-pointer"
              style={{ accentColor: accent }}
            />
            <label className="text-[13px]" style={{ color: palette.inputText }}>
              {field.label}
              {field.required && <span className="text-red-400 ml-0.5">*</span>}
            </label>
          </div>
        );

      default:
        // text, email, phone
        return (
          <div key={field.field_id} className="mb-1.5">
            <input
              type={field.type === 'phone' ? 'tel' : field.type}
              placeholder={placeholder}
              value={value}
              onChange={(e) => setFormData(prev => ({ ...prev, [field.field_id]: e.target.value }))}
              className={inputClass}
              style={baseStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
            {error && <p className="text-[11px] text-red-400 mt-0.5 mb-0">{error}</p>}
          </div>
        );
    }
  };

  return (
    <div
      className="mt-2.5 pt-2.5 animate-[cwSlideUp_0.2s_ease-out]"
      style={{ borderTop: `1px solid ${palette.divider}` }}
    >
      <p
        className="m-0 mb-2 text-[12px] font-semibold"
        style={{ color: palette.subtleText }}
      >
        {title}
      </p>
      {fields.map(renderField)}
      <button
        onClick={handleFormSubmit}
        disabled={!isFormValid}
        className="w-full py-2.5 rounded-lg border-none text-white cursor-pointer font-semibold text-[13px] transition-all duration-150 active:scale-98"
        style={{
          backgroundColor: accent,
          opacity: isFormValid ? 1 : 0.5,
        }}
      >
        Submit
      </button>
    </div>
  );
}
