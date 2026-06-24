export const SESSION_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours
export const HISTORY_STORAGE_KEY_PREFIX = 'cw_history_';

export const getSessionId = (): string => {
  const match = document.cookie.match(/(?:^|;\s*)chat_session_id=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
};

export const WIDGET_WIDTH = '380px';
export const WIDGET_HEIGHT = '560px';
export const MOBILE_WIDGET_HEIGHT = '75dvh';

export const DRAG_HANDLE_WIDTH = '36px';
export const DRAG_HANDLE_HEIGHT = '4px';

export const TYPING_DOT_SIZE = '7px';
export const TYPING_INDICATOR_BOUNCE_DELAY = 150;
export const SCROLL_INTO_VIEW_DELAY = 50;

export const DEFAULT_FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
