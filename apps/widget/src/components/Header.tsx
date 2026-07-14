import { useRef, useEffect } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { Palette } from '../utils/theme';

interface HeaderProps {
  palette: Palette;
  onClose: () => void;
  onNewSession: () => void;
  onHistory: () => void;
  onPointerDown?: (event: ReactPointerEvent<HTMLDivElement>) => void;
  profileColor?: string | null;
}

export function Header({ palette, onClose, onNewSession, onHistory, onPointerDown, profileColor }: HeaderProps) {
  const headerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = headerRef.current;
    if (!el || !onPointerDown) return;
    el.style.setProperty('touch-action', 'none', 'important');
    const preventTouch = (e: TouchEvent) => {
      if ((e.target as HTMLElement | null)?.closest('button, a, input, textarea, select')) return;
      e.preventDefault();
    };
    el.addEventListener('touchstart', preventTouch, { passive: false });
    return () => el.removeEventListener('touchstart', preventTouch);
  }, [onPointerDown]);

  return (
    <div
      ref={headerRef}
      className="px-5 py-4 flex justify-between items-center shrink-0"
      onPointerDown={onPointerDown}
      style={{
        background: palette.headerBg,
        color: palette.headerText,
        cursor: onPointerDown ? 'grab' : undefined,
        touchAction: onPointerDown ? 'none' : undefined,
        userSelect: onPointerDown ? 'none' : undefined,
      }}
    >
      <div className="flex items-center gap-2.5">
        <div className="w-8.5 h-8.5 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1.5 4.5-3 6v1a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1v-1c-1.5-1.5-3-3.5-3-6a7 7 0 0 1 7-7z" />
            <path d="M9 21h6" />
          </svg>
        </div>
        <div>
          <h3 className="m-0 text-[15px] font-semibold tracking-tight">AI Assistant</h3>
          <p className="m-0 text-[11px] opacity-70 tracking-wider">Online — ready to help</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {profileColor && (
          <div
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: profileColor }}
            title="Visitor profile recognized"
          />
        )}
        <button
          onClick={onHistory}
          aria-label="Chat History"
          className="w-8 h-8 rounded-lg bg-white/15 border-none cursor-pointer flex items-center justify-center transition-colors duration-150 hover:bg-white/25"
          style={{ color: palette.headerText }}
          title="Chat History"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </button>
        <button
          onClick={onNewSession}
          aria-label="New Chat"
          className="w-8 h-8 rounded-lg bg-white/15 border-none cursor-pointer flex items-center justify-center transition-colors duration-150 hover:bg-white/25"
          style={{ color: palette.headerText }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
        <button
          onClick={onClose}
          aria-label="Close chat"
          className="w-8 h-8 rounded-lg bg-white/15 border-none cursor-pointer flex items-center justify-center text-[18px] transition-colors duration-150 leading-none hover:bg-white/25"
          style={{ color: palette.headerText }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  );
}
