const DEFAULT_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export interface WidgetConfig {
  theme?: string;
  suggested_questions?: string[];
  show_sources?: boolean;
}

export interface EnquiryData {
  name: string;
  email: string;
  phone?: string;
  message: string;
  session_id: string;
}

async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

class ApiClient {
  private apiKey: string = '';
  private apiBaseUrl: string = DEFAULT_API_BASE_URL;

  public init(apiKey: string, apiBaseUrl?: string) {
    this.apiKey = apiKey;
    if (apiBaseUrl) {
      this.apiBaseUrl = apiBaseUrl.replace(/\/$/, "");
    }
  }

  public async connectChatSocket(): Promise<WebSocket> {
    const keyHash = await sha256(this.apiKey);
    const protocol = this.apiBaseUrl.startsWith('https') ? 'wss' : 'ws';
    const host = this.apiBaseUrl.replace(/^https?:\/\//, '');
    const url = `${protocol}://${host}/ws/chat?key_hash=${keyHash}`;
    return new WebSocket(url);
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (this.apiKey) {
      headers.set("Authorization", `Bearer ${this.apiKey}`);
    }
    if (options.method && options.method !== 'GET' && !headers.has('Content-Type')) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${this.apiBaseUrl}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      throw new Error(`Request to ${path} failed with status ${response.status}`);
    }

    return response.json();
  }

  public getWidgetConfig(): Promise<WidgetConfig> {
    return this.request<WidgetConfig>("/widget/config", {
      method: "GET",
    });
  }

  public submitEnquiry(data: EnquiryData): Promise<any> {
    return this.request<any>("/leads", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  public submitFeedback(messageId: string, sessionId: string, rating: 'like' | 'dislike'): Promise<any> {
    return this.request<any>("/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, session_id: sessionId, rating }),
    });
  }
}

export const apiClient = new ApiClient();

export const getWidgetConfig = () =>
  apiClient.getWidgetConfig();

export const submitEnquiry = (data: EnquiryData) =>
  apiClient.submitEnquiry(data);

export const submitFeedback = (messageId: string, sessionId: string, rating: 'like' | 'dislike') =>
  apiClient.submitFeedback(messageId, sessionId, rating);
