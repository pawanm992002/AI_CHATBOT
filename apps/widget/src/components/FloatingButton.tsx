import { Palette } from '../utils/theme';

interface FloatingButtonProps {
  accent: string;
  palette: Palette;
  onOpen: () => void;
  hasMessages: boolean;
}

export function FloatingButton({ accent, palette, onOpen, hasMessages }: FloatingButtonProps) {
  return (
    <button
      onClick={onOpen}
      aria-label="Open chat"
      className="w-[60px] h-[60px] rounded-full text-white border-none cursor-pointer flex items-center justify-center transition-all duration-200 ease-out hover:scale-108"
      style={{
        background: `linear-gradient(135deg, ${accent}, ${accent}CC)`,
        boxShadow: `0 4px 20px ${palette.fabShadow}`,
        animation: !hasMessages ? 'cwPulse 3s ease-in-out 2' : 'none',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = `0 6px 28px ${palette.fabShadow}`;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = `0 4px 20px ${palette.fabShadow}`;
      }}
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    </button>
  );
}
