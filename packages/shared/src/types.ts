export interface Source {
  section_title?: string;
  title?: string;
  section_path?: string;
  url?: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  messageId?: string;
  sources?: Source[];
  showEnquiryForm?: boolean;
  enquirySubmitted?: boolean;
  feedback?: 'like' | 'dislike' | null;
  isStreaming?: boolean;
}

export interface ThemeState {
  accent: string;
  font: string;
  isDark: boolean;
}

export interface WidgetProps {
  apiKey: string;
  apiBaseUrl?: string;
}
