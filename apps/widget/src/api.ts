const DEFAULT_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export interface LeadFormFieldConfig {
  field_id: string;
  label: string;
  type: 'text' | 'email' | 'phone' | 'textarea' | 'select' | 'checkbox';
  required: boolean;
  placeholder?: string;
  options?: string[];
  order: number;
}

export interface LeadFormConfig {
  form_id: string;
  title: string;
  fields: LeadFormFieldConfig[];
  trigger_instructions: string;
  enabled: boolean;
}

export interface WidgetConfig {
  theme?: string;
  suggested_questions?: string[];
  show_sources?: boolean;
  lead_form?: LeadFormConfig | null;
}

export interface EnquiryData {
  form_id?: string;
  name?: string;
  email?: string;
  phone?: string;
  message?: string;
  session_id: string;
  visitor_id?: string;
  custom_fields?: Record<string, string>;
}

function sha256Fallback(ascii: string): string {
  function rightRotate(value: number, amount: number) {
    return (value >>> amount) | (value << (32 - amount));
  }
  const mathPow = Math.pow;
  const maxWord = mathPow(2, 32);
  let i, j;
  let result = '';
  const words: number[] = [];
  const asciiLength = ascii.length * 8;
  let hash: number[] = [];
  const k: number[] = [];
  let primeCounter = 0;
  const isComposite: { [key: number]: number } = {};
  for (let candidate = 2; primeCounter < 64; candidate++) {
    if (!isComposite[candidate]) {
      for (i = 0; i < 313; i += candidate) {
        isComposite[i] = 1;
      }
      hash[primeCounter] = (mathPow(candidate, .5) * maxWord) | 0;
      k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
    }
  }
  ascii += '\x80';
  while (ascii.length % 64 - 56) {
    ascii += '\x00';
  }
  for (i = 0; i < ascii.length; i++) {
    const charCode = ascii.charCodeAt(i);
    if (charCode >> 8) return '';
    words[i >> 2] |= charCode << (24 - i % 4 * 8);
  }
  words[words.length] = ((asciiLength / maxWord) | 0);
  words[words.length] = (asciiLength | 0);
  for (j = 0; j < words.length;) {
    const w = words.slice(j, j += 16);
    const oldHash = hash.slice(0);
    for (i = 0; i < 64; i++) {
      const temp1 = i < 16 ? w[i] : (
        rightRotate(w[i - 2], 17) ^ rightRotate(w[i - 2], 19) ^ (w[i - 2] >>> 10)
      ) + w[i - 7] + (
          rightRotate(w[i - 15], 7) ^ rightRotate(w[i - 15], 18) ^ (w[i - 15] >>> 3)
        ) + w[i - 16];
      if (i >= 16) {
        w[i] = temp1 | 0;
      }
      const a = hash[0], e = hash[4];
      const temp2 = (
        rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)
      ) + (
          (a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2])
        );
      const temp3 = hash[7] + (
        rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)
      ) + (
          (e & hash[5]) ^ (~e & hash[6])
        ) + k[i] + (w[i] | 0);
      hash = [
        (temp3 + temp2) | 0,
        a,
        hash[1],
        hash[2],
        ((hash[3] + temp3) | 0),
        e,
        hash[5],
        hash[6]
      ];
    }
    for (i = 0; i < 8; i++) {
      hash[i] = (hash[i] + oldHash[i]) | 0;
    }
  }
  for (i = 0; i < 8; i++) {
    for (j = 3; j + 1; j--) {
      const b = (hash[i] >> (j * 8)) & 255;
      result += (b < 16 ? '0' : '') + b.toString(16);
    }
  }
  return result;
}

async function sha256(message: string): Promise<string> {
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const msgBuffer = new TextEncoder().encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }
  return sha256Fallback(message);
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
    const url = `${protocol}://${host}/api/ws/chat?key_hash=${keyHash}`;
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

    const cleanPath = path.startsWith('/api') ? path : `/api${path}`;
    const response = await fetch(`${this.apiBaseUrl}${cleanPath}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let detail = `Request to ${path} failed with status ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          detail = errorData.detail;
        }
      } catch (e) {
        // Not JSON
      }
      throw new Error(detail);
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

  public getLeadFormById(formId: string): Promise<LeadFormConfig | null> {
    return this.request<LeadFormConfig | null>(`/widget/lead-form/${formId}`, {
      method: "GET",
    });
  }

  public submitFeedback(messageId: string, sessionId: string, rating: 'like' | 'dislike', visitorId?: string): Promise<any> {
    return this.request<any>("/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, session_id: sessionId, rating, visitor_id: visitorId }),
    });
  }
}

export const apiClient = new ApiClient();

export const getWidgetConfig = () =>
  apiClient.getWidgetConfig();

export const submitEnquiry = (data: EnquiryData) =>
  apiClient.submitEnquiry(data);

export const getLeadFormById = (formId: string) =>
  apiClient.getLeadFormById(formId);

export const submitFeedback = (messageId: string, sessionId: string, rating: 'like' | 'dislike', visitorId?: string) =>
  apiClient.submitFeedback(messageId, sessionId, rating, visitorId);
