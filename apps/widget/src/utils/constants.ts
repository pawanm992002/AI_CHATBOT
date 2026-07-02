export const SESSION_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours
export const HISTORY_STORAGE_KEY_PREFIX = 'cw_history_';
export const VISITOR_STORAGE_KEY = 'cw_visitor_id';
export const SESSION_STORAGE_KEY = 'cw_session_id';

export function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

export function getVisitorId(): string {
  let id = localStorage.getItem(VISITOR_STORAGE_KEY);
  if (!id) {
    id = generateId();
    localStorage.setItem(VISITOR_STORAGE_KEY, id);
  }
  return id;
}

export function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!id) {
    id = generateId();
    sessionStorage.setItem(SESSION_STORAGE_KEY, id);
  }
  return id;
}

export function resetSessionId(): string {
  const id = generateId();
  sessionStorage.setItem(SESSION_STORAGE_KEY, id);
  return id;
}


export const WIDGET_WIDTH = '380px';
export const WIDGET_HEIGHT = '560px';
export const MOBILE_WIDGET_HEIGHT = '75dvh';

export const DRAG_HANDLE_WIDTH = '36px';
export const DRAG_HANDLE_HEIGHT = '4px';

export const TYPING_DOT_SIZE = '7px';
export const TYPING_INDICATOR_BOUNCE_DELAY = 150;
export const SCROLL_INTO_VIEW_DELAY = 50;

export const DEFAULT_FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
