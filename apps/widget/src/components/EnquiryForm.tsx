import { useState } from 'react';
import { Palette } from '../utils/theme';

interface EnquiryFormProps {
  accent: string;
  palette: Palette;
  onSubmit: (data: { name: string; email: string; phone: string }) => void;
}

export function EnquiryForm({ accent, palette, onSubmit }: EnquiryFormProps) {
  const [formData, setFormData] = useState({ name: '', email: '', phone: '' });

  const handleFormSubmit = () => {
    if (!formData.name.trim() || !formData.email.trim()) return;
    onSubmit(formData);
  };

  const inputClass = "w-full px-3 py-2.25 mb-1.5 rounded-lg border outline-none text-[13px] box-border transition-colors duration-150";

  return (
    <div 
      className="mt-2.5 pt-2.5 animate-[cwSlideUp_0.2s_ease-out]"
      style={{ borderTop: `1px solid ${palette.divider}` }}
    >
      <p 
        className="m-0 mb-2 text-[12px] font-semibold"
        style={{ color: palette.subtleText }}
      >
        Leave your details and we'll get back to you:
      </p>
      <input
        type="text"
        placeholder="Your Name *"
        value={formData.name}
        onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
        className={inputClass}
        style={{
          borderColor: palette.inputBorder,
          backgroundColor: palette.inputBg,
          color: palette.inputText,
        }}
        onFocus={e => e.currentTarget.style.borderColor = accent}
        onBlur={e => e.currentTarget.style.borderColor = palette.inputBorder}
      />
      <input
        type="email"
        placeholder="Your Email *"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        className={inputClass}
        style={{
          borderColor: palette.inputBorder,
          backgroundColor: palette.inputBg,
          color: palette.inputText,
        }}
        onFocus={e => e.currentTarget.style.borderColor = accent}
        onBlur={e => e.currentTarget.style.borderColor = palette.inputBorder}
      />
      <input
        type="tel"
        placeholder="Phone (optional)"
        value={formData.phone}
        onChange={(e) => setFormData(prev => ({ ...prev, phone: e.target.value }))}
        className="w-full px-3 py-2.25 mb-2 rounded-lg border outline-none text-[13px] box-border transition-colors duration-150"
        style={{
          borderColor: palette.inputBorder,
          backgroundColor: palette.inputBg,
          color: palette.inputText,
        }}
        onFocus={e => e.currentTarget.style.borderColor = accent}
        onBlur={e => e.currentTarget.style.borderColor = palette.inputBorder}
      />
      <button
        onClick={handleFormSubmit}
        disabled={!formData.name.trim() || !formData.email.trim()}
        className="w-full py-2.5 rounded-lg border-none text-white cursor-pointer font-semibold text-[13px] transition-all duration-150 active:scale-98"
        style={{
          backgroundColor: accent,
          opacity: formData.name.trim() && formData.email.trim() ? 1 : 0.5,
        }}
      >
        Submit
      </button>
    </div>
  );
}
