import { useState, useMemo } from 'react';
import { Palette } from '../utils/theme';
import { ConversationSummary } from '../api';

interface SessionHistoryProps {
  palette: Palette;
  sessions: ConversationSummary[];
  accent: string;
  isDark: boolean;
  loading?: boolean;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onBack: () => void;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diff < 604800000) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function SessionHistory({ palette, sessions, accent, isDark, loading, onSelectSession, onNewChat, onBack }: SessionHistoryProps) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions;
    const q = search.toLowerCase();
    return sessions.filter(s => s.preview.toLowerCase().includes(q));
  }, [sessions, search]);

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: palette.msgAreaBg }}>
      <div className="px-4 py-3.5 flex items-center gap-2 shrink-0" style={{ borderBottom: `1px solid ${palette.divider}` }}>
        <button
          onClick={onBack}
          className="w-8 h-8 rounded-lg bg-white/10 border-none cursor-pointer flex items-center justify-center shrink-0 transition-colors duration-150 hover:bg-white/20"
          style={{ color: palette.inputText }}
          aria-label="Back to chat"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
        </button>
        <h3 className="m-0 text-[14px] font-semibold flex-1" style={{ color: palette.inputText }}>
          Chat History
        </h3>
        <button
          onClick={onNewChat}
          className="px-3 py-1.5 rounded-lg border-none cursor-pointer text-[12px] font-semibold transition-opacity duration-150 hover:opacity-90"
          style={{ backgroundColor: accent, color: '#fff' }}
        >
          + New Chat
        </button>
      </div>

      <div className="p-3 pb-2 shrink-0">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2"
            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            style={{ color: palette.subtleText, opacity: 0.6 }}
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search conversations..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 rounded-xl text-[13px] border outline-none transition-all duration-150"
            style={{
              backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : '#f1f5f9',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0',
              color: palette.inputText,
            }}
            onFocus={e => { e.currentTarget.style.borderColor = accent; }}
            onBlur={e => { e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'; }}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {loading ? (
          <div className="flex items-center justify-center mt-12">
            <div
              className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: isDark ? 'rgba(255,255,255,0.2)' : '#e2e8f0', borderTopColor: accent }}
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center mt-12 text-center px-6">
            <div className="w-11 h-11 rounded-2xl flex items-center justify-center mb-3" style={{ background: `${accent}15` }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <p className="text-[13px] m-0 leading-relaxed" style={{ color: palette.subtleText }}>
              {search ? 'No matching conversations found' : 'No conversations yet'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {filtered.map(session => (
              <button
                key={session.session_id}
                onClick={() => onSelectSession(session.session_id)}
                className="w-full text-left p-3 rounded-xl border cursor-pointer transition-all duration-150"
                style={{
                  borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
                  backgroundColor: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.8)',
                }}
                onMouseEnter={e => { e.currentTarget.style.backgroundColor = isDark ? 'rgba(255,255,255,0.1)' : '#f8fafc'; }}
                onMouseLeave={e => { e.currentTarget.style.backgroundColor = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.8)'; }}
              >
                <p
                  className="m-0 text-[13px] leading-relaxed"
                  style={{
                    color: palette.inputText,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {session.preview || 'No messages'}
                </p>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[11px]" style={{ color: palette.subtleText }}>
                    {session.message_count} {session.message_count === 1 ? 'message' : 'messages'}
                  </span>
                  <span className="text-[11px]" style={{ color: palette.subtleText }}>·</span>
                  <span className="text-[11px]" style={{ color: palette.subtleText }}>
                    {formatDate(session.created_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}