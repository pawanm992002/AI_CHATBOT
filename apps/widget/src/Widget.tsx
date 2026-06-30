import { useState, useEffect, useRef, useCallback, useMemo, CSSProperties } from 'react';
import { submitEnquiry, getWidgetConfig, submitFeedback, apiClient, LeadFormConfig } from './api';
import { WidgetProps, Message, useIsMobile, useStyleInjection } from '@chatbot/shared';
import { getPalette } from './utils/theme';
import { useHostTheme } from './hooks/useHostTheme';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Header } from './components/Header';
import { FloatingButton } from './components/FloatingButton';
import { MessageList } from './components/MessageList';
import { InputArea } from './components/InputArea';
import {
  SESSION_EXPIRY_MS,
  HISTORY_STORAGE_KEY_PREFIX,
  WIDGET_WIDTH,
  WIDGET_HEIGHT,
  MOBILE_WIDGET_HEIGHT,
  DRAG_HANDLE_WIDTH,
  DRAG_HANDLE_HEIGHT,
  SCROLL_INTO_VIEW_DELAY,
  getSessionId
} from './utils/constants';

export const Widget = ({ apiKey, apiBaseUrl }: WidgetProps) => {
  apiClient.init(apiKey, apiBaseUrl);

  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => {
    if (!apiKey) return [];
    try {
      const stored = sessionStorage.getItem(`${HISTORY_STORAGE_KEY_PREFIX}${apiKey}`);
      if (stored) {
        const { messages: storedMessages, lastInteractionTime } = JSON.parse(stored);
        const isExpired = Date.now() - lastInteractionTime > SESSION_EXPIRY_MS;
        if (!isExpired) {
          return storedMessages;
        }
      }
    } catch (e) {
      console.error("Failed to load chat history from sessionStorage", e);
    }
    return [];
  });
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [showSources, setShowSources] = useState<boolean>(true);
  const [leadFormConfig, setLeadFormConfig] = useState<LeadFormConfig | null>(null);
  const [isDisabled, setIsDisabled] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useStyleInjection();
  const hostTheme = useHostTheme();
  const isMobile = useIsMobile();

  const accent = hostTheme.accent;
  const isDark = hostTheme.isDark;
  const font = hostTheme.font;

  const widgetVars = useMemo(() => ({
    '--widget-accent': accent,
    '--widget-font': font,
  }), [accent, font]) as CSSProperties;

  const palette = useMemo(() => getPalette(accent, isDark), [accent, isDark]);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const config = await getWidgetConfig();
        if (config?.suggested_questions) setSuggestedQuestions(config.suggested_questions);
        if (config && typeof config.show_sources === 'boolean') {
          setShowSources(config.show_sources);
        }
        if (config?.lead_form) {
          setLeadFormConfig(config.lead_form);
        }
      } catch (err: any) {
        console.error("Failed to fetch widget config", err);
        if (err.message && err.message.includes("Tenant is disabled")) {
          setIsDisabled(true);
        }
      }
    };
    fetchConfig();
  }, [apiKey]);

  // Persist chat history on updates
  useEffect(() => {
    if (!apiKey) return;
    if (messages.length > 0) {
      try {
        const data = {
          messages,
          lastInteractionTime: Date.now()
        };
        sessionStorage.setItem(`${HISTORY_STORAGE_KEY_PREFIX}${apiKey}`, JSON.stringify(data));
      } catch (e) {
        console.error("Failed to save chat history to sessionStorage", e);
      }
    }
  }, [messages, apiKey]);

  useEffect(() => {
    const timer = setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, SCROLL_INTO_VIEW_DELAY);
    return () => clearTimeout(timer);
  }, [messages, isLoading]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  const clearEnquiryForms = useCallback(() => {
    setMessages(prev => prev.map(m => {
      if (m.role === 'assistant' && m.showEnquiryForm && !m.enquirySubmitted) {
        return { ...m, showEnquiryForm: false };
      }
      return m;
    }));
  }, []);

  const getWs = useCallback(async (): Promise<WebSocket> => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return wsRef.current;
    }

    // Close any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = await apiClient.connectChatSocket();

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        ws.close();
        reject(new Error('WebSocket connection timeout'));
      }, 10000);

      ws.onopen = () => {
        // Wait for authenticated message
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'authenticated') {
          clearTimeout(timeout);
          wsRef.current = ws;
          resolve(ws);
        }
      };

      ws.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('WebSocket connection failed'));
      };

      ws.onclose = (event) => {
        clearTimeout(timeout);
        if (event.code === 4001) {
          reject(new Error('Invalid API key'));
        } else if (!wsRef.current) {
          reject(new Error('WebSocket closed'));
        }
        wsRef.current = null;
      };
    });
  }, []);

  const handleSend = useCallback(async (text: string) => {
    if (!text.trim()) return;

    clearEnquiryForms();

    const userMsg: Message = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    // Add placeholder for streaming response
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      isStreaming: true,
      enquirySubmitted: false,
      feedback: null,
    }]);

    try {
      const ws = await getWs();

      // Set up message handler for this request
      const originalOnMessage = ws.onmessage;
      let messageComplete = false;

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'sources':
            setMessages(prev => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx].role === 'assistant') {
                updated[idx] = { ...updated[idx], sources: data.data };
              }
              return updated;
            });
            break;

          case 'token':
            setMessages(prev => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx].role === 'assistant') {
                updated[idx] = { ...updated[idx], content: updated[idx].content + data.content };
              }
              return updated;
            });
            break;

          case 'enquiry_form':
            setMessages(prev => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx].role === 'assistant') {
                updated[idx] = { ...updated[idx], showEnquiryForm: true, enquiryFormId: data.form_id || '' };
              }
              return updated;
            });
            if (data.form_id) {
              apiClient.getLeadFormById(data.form_id).then(form => {
                if (form) setLeadFormConfig(form);
              }).catch(() => {});
            }
            break;

          case 'done':
            messageComplete = true;
            setMessages(prev => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx].role === 'assistant') {
                const cleanAnswer = data.answer || updated[idx].content;
                updated[idx] = { ...updated[idx], content: cleanAnswer, messageId: data.message_id, isStreaming: false };
              }
              return updated;
            });
            ws.onmessage = originalOnMessage;
            setIsLoading(false);
            break;

          case 'error':
            messageComplete = true;
            setMessages(prev => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx].role === 'assistant') {
                updated[idx] = { ...updated[idx], content: data.detail || 'An error occurred.', isStreaming: false };
              }
              return updated;
            });
            ws.onmessage = originalOnMessage;
            setIsLoading(false);
            break;
        }
      };

      // Send the chat message
      ws.send(JSON.stringify({
        type: 'message',
        query: text,
        current_url: window.location.href,
        current_page_title: document.title,
        session_id: getSessionId(),
      }));

      // Safety timeout — if stream doesn't complete in 60s, reset loading state
      setTimeout(() => {
        if (!messageComplete) {
          setMessages(prev => {
            const updated = [...prev];
            const idx = updated.length - 1;
            if (updated[idx]?.role === 'assistant' && updated[idx].isStreaming) {
              updated[idx] = { ...updated[idx], isStreaming: false };
            }
            return updated;
          });
          ws.onmessage = originalOnMessage;
          setIsLoading(false);
        }
      }, 60000);

    } catch (error) {
      console.error("Chat error:", error);
      setMessages(prev => {
        const updated = [...prev];
        const idx = updated.length - 1;
        if (updated[idx]?.role === 'assistant') {
          updated[idx] = { ...updated[idx], content: 'Sorry, an error occurred.', isStreaming: false };
        } else {
          updated.push({ role: 'assistant', content: 'Sorry, an error occurred.' });
        }
        return updated;
      });
      setIsLoading(false);
    }
  }, [clearEnquiryForms, getWs]);

  const handleEnquirySubmit = useCallback(async (msgIndex: number, formData: { custom_fields: Record<string, string>; form_id?: string }) => {
    const contextMessages = messages.slice(Math.max(0, msgIndex - 5), msgIndex + 1);
    const contextText = contextMessages
      .map(m => `${m.role === 'user' ? 'Visitor' : 'Bot'}: ${m.content}`)
      .join('\n');

    try {
      await submitEnquiry({
        form_id: formData.form_id,
        custom_fields: formData.custom_fields,
        message: contextText,
        session_id: getSessionId(),
      });

      setMessages(prev => prev.map((m, i) =>
        i === msgIndex ? { ...m, enquirySubmitted: true } : m
      ));
    } catch (error) {
      console.error("Enquiry submit error:", error);
    }
  }, [messages]);

  const handleFeedback = useCallback(async (msgIndex: number, rating: 'like' | 'dislike') => {
    const msg = messages[msgIndex];
    if (!msg || !msg.messageId || msg.feedback === rating) return;

    try {
      await submitFeedback(msg.messageId, getSessionId(), rating);
      setMessages(prev => prev.map((m, i) =>
        i === msgIndex ? { ...m, feedback: rating } : m
      ));
    } catch (error) {
      console.error("Feedback error:", error);
    }
  }, [messages]);

  return (
    <div
      className="cw-widget-root"
      style={{
        position: 'fixed',
        bottom: isMobile ? (isOpen ? 0 : '16px') : '24px',
        right: isMobile ? (isOpen ? 0 : '16px') : '24px',
        zIndex: 2147483647,
        fontFamily: font,
        ...widgetVars,
      }}
    >
      {isOpen ? (
        <>
          {/* Mobile backdrop overlay */}
          {isMobile && (
            <div
              onClick={() => setIsOpen(false)}
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0,0,0,0.5)',
                zIndex: 2147483646,
                animation: 'cwFadeIn 0.2s ease-out',
              }}
            />
          )}
          <div
            className="flex flex-col overflow-hidden z-[2147483647]"
            style={{
              width: isMobile ? '100vw' : WIDGET_WIDTH,
              height: isMobile ? MOBILE_WIDGET_HEIGHT : WIDGET_HEIGHT,
              position: isMobile ? 'fixed' : 'relative',
              bottom: isMobile ? 0 : undefined,
              right: isMobile ? 0 : undefined,
              borderRadius: isMobile ? '24px 24px 0 0' : '24px',
              background: palette.containerBg,
              backdropFilter: isMobile ? 'none' : 'blur(16px) saturate(180%)',
              WebkitBackdropFilter: isMobile ? 'none' : 'blur(16px) saturate(180%)',
              border: isMobile ? 'none' : `1px solid ${palette.containerBorder}`,
              boxShadow: isMobile
                ? '0 -4px 24px rgba(0,0,0,0.15)'
                : isDark
                  ? '0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04)'
                  : '0 12px 40px rgba(0,0,0,0.12), 0 0 0 1px rgba(255,255,255,0.6)',
              animation: isMobile
                ? 'cwSlideUpMobile 0.3s cubic-bezier(0.16,1,0.3,1)'
                : 'cwFadeIn 0.3s cubic-bezier(0.16,1,0.3,1)',
              fontFamily: font,
            }}
          >

            {/* Mobile drag handle */}
            {isMobile && (
              <div
                className="flex justify-center pt-3 pb-1"
                style={{ background: palette.headerBg }}
              >
                <div
                  className="rounded"
                  style={{
                    width: DRAG_HANDLE_WIDTH,
                    height: DRAG_HANDLE_HEIGHT,
                    background: 'rgba(255,255,255,0.4)',
                  }}
                />
              </div>
            )}

            {/* Header */}
            <Header palette={palette} onClose={() => setIsOpen(false)} />

            {/* Messages area */}
            {isDisabled ? (
              <div 
                className="flex-1 flex flex-col items-center justify-center p-6 text-center animate-fadeIn"
                style={{ background: palette.msgAreaBg || 'transparent' }}
              >
                <div 
                  className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-500 border border-rose-500/20 mb-4 animate-pulse"
                >
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </div>
                <h3 className="font-bold text-sm" style={{ color: palette.inputText }}>Service Blocked</h3>
                <p className="text-xs mt-2 max-w-[200px] leading-relaxed" style={{ color: palette.subtleText }}>
                  Tenant is disabled. Please contact the administrator.
                </p>
              </div>
            ) : (
              <>
                <div className="flex-1 flex flex-col overflow-hidden relative">
                  <ErrorBoundary>
                    <MessageList
                      messages={messages}
                      suggestedQuestions={suggestedQuestions}
                      accent={accent}
                      isDark={isDark}
                      palette={palette}
                      onSend={handleSend}
                      onFeedback={handleFeedback}
                      onEnquirySubmit={handleEnquirySubmit}
                      showSources={showSources}
                      leadFormConfig={leadFormConfig}
                    />
                  </ErrorBoundary>

                  <div ref={messagesEndRef} />
                </div>

                {/* Input area */}
                <InputArea
                  isLoading={isLoading}
                  accent={accent}
                  font={font}
                  isDark={isDark}
                  palette={palette}
                  onSend={handleSend}
                />
              </>
            )}
          </div>
        </>
      ) : (
        /* Floating Action Button */
        <FloatingButton
          accent={accent}
          palette={palette}
          onOpen={() => setIsOpen(true)}
          hasMessages={messages.length > 0}
        />
      )}
    </div>
  );
};
