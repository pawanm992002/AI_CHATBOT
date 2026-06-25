import { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Message } from '@chatbot/shared';
import { Palette } from '../utils/theme';
import { EnquiryForm } from './EnquiryForm';
import { SCROLL_INTO_VIEW_DELAY } from '../utils/constants';

interface MessageListProps {
  messages: Message[];
  suggestedQuestions: string[];
  accent: string;
  isDark: boolean;
  palette: Palette;
  onSend: (text: string) => void;
  onFeedback: (msgIndex: number, rating: 'like' | 'dislike') => void;
  onEnquirySubmit: (msgIndex: number, formData: { name: string; email: string; phone: string }) => void;
  showSources: boolean;
}

export function MessageList({
  messages,
  suggestedQuestions,
  accent,
  isDark,
  palette,
  onSend,
  onFeedback,
  onEnquirySubmit,
  showSources,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Scroll to bottom after a short delay to allow DOM to update
    const timer = setTimeout(() => {
      el.scrollTop = el.scrollHeight;
    }, SCROLL_INTO_VIEW_DELAY);
    return () => clearTimeout(timer);
  }, [messages]);

  return (
    <div
      ref={scrollRef}
      className="flex-1 p-4 overflow-y-auto flex flex-col gap-2.5"
      style={{ backgroundColor: palette.msgAreaBg }}
    >
      {/* Empty state — suggested questions */}
      {messages.length === 0 && suggestedQuestions.length > 0 && (
        <div className="my-auto">
          <p
            className="text-center text-[12px] mb-2.5 font-semibold tracking-wider uppercase"
            style={{ color: palette.subtleText }}
          >
            Suggested
          </p>
          <div className="flex flex-col gap-2">
            {suggestedQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => onSend(q)}
                className="px-3.5 py-2.5 rounded-xl text-left text-[13px] font-semibold cursor-pointer border transition-all duration-150 leading-relaxed"
                style={{
                  borderColor: isDark ? 'rgba(255,255,255,0.2)' : `${accent}30`,
                  backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : `${accent}08`,
                  color: isDark ? '#fff' : accent,
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.backgroundColor = isDark ? 'rgba(255,255,255,0.14)' : `${accent}18`;
                  e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.3)' : `${accent}50`;
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.backgroundColor = isDark ? 'rgba(255,255,255,0.08)' : `${accent}08`;
                  e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.2)' : `${accent}30`;
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Empty state — no suggestions */}
      {messages.length === 0 && suggestedQuestions.length === 0 && (
        <div className="my-auto text-center px-5">
          <div
            className="w-13 h-13 rounded-2xl flex items-center justify-center mx-auto mb-3.5"
            style={{ background: `${accent}15` }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <p
            className="text-[14px] m-0 leading-relaxed"
            style={{ color: palette.subtleText }}
          >
            Ask me anything about this site!
          </p>
        </div>
      )}

      {/* Message list */}
      {messages.map((m, i) => (
        <div
          key={i}
          className="max-w-[85%] animate-[cwSlideUp_0.25s_cubic-bezier(0.16,1,0.3,1)]"
          style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
          }}
        >
          <div
            className="px-3.5 py-2.5 leading-relaxed text-[14px] break-words"
            style={{
              borderRadius: m.role === 'user'
                ? '18px 18px 4px 18px'
                : '18px 18px 18px 4px',
              backgroundColor: m.role === 'user'
                ? palette.userBubbleBg
                : palette.assistantBubbleBg,
              color: m.role === 'user'
                ? palette.userBubbleText
                : palette.assistantBubbleText,
              border: m.role === 'user'
                ? 'none'
                : `1px solid ${palette.assistantBubbleBorder}`,
              boxShadow: m.role === 'user'
                ? `0 2px 10px ${accent}25`
                : isDark
                  ? '0 1px 3px rgba(0,0,0,0.2)'
                  : '0 1px 4px rgba(0,0,0,0.04)',
            }}
          >
            {m.role === 'user' ? (
              m.content
            ) : (
              <>
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline underline-offset-2"
                        style={{ color: accent }}
                      >
                        {children}
                      </a>
                    ),
                    strong: ({ children }) => (
                      <strong className="font-semibold">{children}</strong>
                    ),
                    p: ({ children }) => (
                      <p className="my-1 leading-relaxed">{children}</p>
                    ),
                    ul: ({ children }) => (
                      <ul className="my-1 pl-5 list-disc">{children}</ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="my-1 pl-5 list-decimal">{children}</ol>
                    ),
                    li: ({ children }) => (
                      <li className="my-0.5">{children}</li>
                    ),
                  }}
                >
                  {m.content}
                </ReactMarkdown>
                {m.isStreaming && (
                  <span
                    className="inline-block w-[7px] h-[7px] ml-[3px] align-middle rounded-full"
                    style={{
                      backgroundColor: accent,
                      animation: 'cwBreathe 1.4s ease-in-out infinite',
                    }}
                  />
                )}
              </>
            )}
          </div>

          {/* Sources */}
          {showSources && m.sources && m.sources.length > 0 && (
            <div
              className="text-[11px] mt-1.5 flex flex-wrap gap-1.5"
              style={{ color: palette.subtleText }}
            >
              {m.sources.map((s, idx) => {
                const label = s.section_title || s.title || `Source ${idx + 1}`;
                const fullTitle = s.section_path || label;
                return (
                  <a
                    key={idx}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={fullTitle}
                    className="inline-flex items-center px-2.5 py-1 rounded-full transition-all duration-150 hover:scale-102 hover:opacity-100 opacity-90 shadow-sm"
                    style={{
                      backgroundColor: isDark ? 'rgba(30, 41, 59, 0.75)' : '#f8fafc',
                      color: isDark ? '#cbd5e1' : '#475569',
                      border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
                      textDecoration: 'none',
                      fontSize: '11px',
                      fontWeight: 500,
                      lineHeight: '1',
                      whiteSpace: 'nowrap',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.backgroundColor = isDark ? 'rgba(255,255,255,0.12)' : '#fff';
                      e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.2)' : `${accent}50`;
                      e.currentTarget.style.color = isDark ? '#fff' : accent;
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.backgroundColor = isDark ? 'rgba(30, 41, 59, 0.75)' : '#f8fafc';
                      e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
                      e.currentTarget.style.color = isDark ? '#cbd5e1' : '#475569';
                    }}
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginRight: '4px', flexShrink: 0 }}>
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                    <span style={{
                      display: 'inline-block',
                      verticalAlign: 'middle',
                      maxWidth: '140px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {label}
                    </span>
                  </a>
                );
              })}
            </div>
          )}

          {/* Feedback buttons */}
          {m.role === 'assistant' && m.messageId && (
            <div className="flex gap-0.5 mt-1">
              <button
                onClick={() => onFeedback(i, 'like')}
                aria-label="Helpful"
                className="bg-none border-none cursor-pointer px-1.25 py-0.75 text-[13px] transition-all duration-150 rounded-md"
                style={{
                  opacity: m.feedback === 'like' ? 1 : 0.35,
                  color: m.feedback === 'like' ? '#22c55e' : palette.subtleText,
                }}
                onMouseEnter={e => { if (!m.feedback) e.currentTarget.style.opacity = '0.7'; }}
                onMouseLeave={e => { if (!m.feedback) e.currentTarget.style.opacity = '0.35'; }}
              >&#128077;</button>
              <button
                onClick={() => onFeedback(i, 'dislike')}
                aria-label="Not helpful"
                className="bg-none border-none cursor-pointer px-1.25 py-0.75 text-[13px] transition-all duration-150 rounded-md"
                style={{
                  opacity: m.feedback === 'dislike' ? 1 : 0.35,
                  color: m.feedback === 'dislike' ? '#ef4444' : palette.subtleText,
                }}
                onMouseEnter={e => { if (!m.feedback) e.currentTarget.style.opacity = '0.7'; }}
                onMouseLeave={e => { if (!m.feedback) e.currentTarget.style.opacity = '0.35'; }}
              >&#128078;</button>
            </div>
          )}

          {/* Enquiry form */}
          {m.showEnquiryForm && !m.enquirySubmitted && (
            <EnquiryForm
              accent={accent}
              palette={palette}
              onSubmit={(formData) => onEnquirySubmit(i, formData)}
            />
          )}

          {/* Enquiry submitted confirmation */}
          {m.showEnquiryForm && m.enquirySubmitted && (
            <div className="mt-2 text-[13px] text-green-500 font-semibold flex items-center gap-1.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Thanks! We'll get back to you soon.
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
