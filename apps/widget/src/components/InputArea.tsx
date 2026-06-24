import React, { useState } from 'react';
import { Palette } from '../utils/theme';

interface InputAreaProps {
  isLoading: boolean;
  accent: string;
  font: string;
  isDark: boolean;
  palette: Palette;
  onSend: (text: string) => void;
}

export function InputArea({
  isLoading,
  accent,
  font,
  isDark,
  palette,
  onSend,
}: InputAreaProps) {
  const [input, setInput] = useState('');

  const handleSendClick = () => {
    if (isLoading || !input.trim()) return;
    onSend(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendClick();
    }
  };

  return (
    <div 
      className="px-3.5 py-3 border-t backdrop-blur-md flex gap-2 items-center shrink-0"
      style={{
        borderTopColor: palette.divider,
        backgroundColor: isDark ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.6)',
      }}
    >
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your message..."
        className="flex-1 px-4 py-2.75 rounded-3xl border outline-none text-[14px] transition-all duration-150"
        style={{
          borderColor: palette.inputBorder,
          backgroundColor: palette.inputBg,
          color: palette.inputText,
          fontFamily: font,
        }}
        onFocus={e => {
          e.currentTarget.style.borderColor = `${accent}60`;
          e.currentTarget.style.boxShadow = `0 0 0 3px ${accent}12`;
        }}
        onBlur={e => {
          e.currentTarget.style.borderColor = palette.inputBorder;
          e.currentTarget.style.boxShadow = 'none';
        }}
      />
      <button
        onClick={handleSendClick}
        disabled={isLoading || !input.trim()}
        aria-label="Send message"
        className="w-10 h-10 rounded-full border-none text-white cursor-pointer flex items-center justify-center transition-all duration-150 shrink-0 active:scale-92"
        style={{
          backgroundColor: accent,
          opacity: isLoading || !input.trim() ? 0.45 : 1,
        }}
        onMouseEnter={e => { if (!isLoading && input.trim()) e.currentTarget.style.opacity = '0.85'; }}
        onMouseLeave={e => { e.currentTarget.style.opacity = isLoading || !input.trim() ? '0.45' : '1'; }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}
