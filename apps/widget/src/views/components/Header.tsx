import { Palette } from '../../utils/theme';

interface HeaderProps {
  palette: Palette;
  onClose: () => void;
}

export function Header({ palette, onClose }: HeaderProps) {
  return (
    <div 
      className="px-5 py-4 flex justify-between items-center shrink-0"
      style={{
        background: palette.headerBg,
        color: palette.headerText,
      }}
    >
      <div className="flex items-center gap-2.5">
        <div className="w-8.5 h-8.5 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1.5 4.5-3 6v1a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1v-1c-1.5-1.5-3-3.5-3-6a7 7 0 0 1 7-7z" />
            <path d="M9 21h6" />
          </svg>
        </div>
        <div>
          <h3 className="m-0 text-[15px] font-semibold tracking-tight">AI Assistant</h3>
          <p className="m-0 text-[11px] opacity-70 tracking-wider">Online — ready to help</p>
        </div>
      </div>
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
  );
}
