export interface Tenant {
  tenant_id: string;
  domain: string;
  plan: 'free' | 'pro' | string;
  created_at: string;
  business_name?: string;
  email?: string;
  status?: 'pending' | 'approved' | 'rejected' | 'disabled';
  api_key?: string;
}

export type SourceType = 'website' | 'pdf' | 'faq' | 'text';

export interface Source {
  source_id: string;
  name: string;
  source_type: SourceType;
  status: 'ready' | 'indexing' | 'failed' | string;
  chunk_count?: number;
  last_indexed_at?: string;
  config?: Record<string, any>;
}

export interface CrawlJob {
  job_id: string;
  url: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  pages_crawled: number;
  error_message?: string;
  created_at: string;
}

export interface FAQ {
  faq_id: string;
  question: string;
  answer: string;
  created_at: string;
}

export interface TextDoc {
  doc_id: string;
  title: string;
  body: string;
  created_at: string;
}

export interface Lead {
  lead_id: string;
  name: string;
  email: string;
  phone?: string;
  message: string;
  form_id?: string;
  custom_fields?: Record<string, string>;
  created_at: string;
}

export interface LeadFormField {
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
  fields: LeadFormField[];
  trigger_instructions: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeGap {
  gap_id: string;
  query: string;
  gap_type?: 'no_context' | 'out_of_scope' | 'knowledge_gap';
  count: number;
  status: 'open' | 'resolved' | 'dismissed';
  last_seen: string;
  url?: string;
  similar_faqs?: {
    faq_id: string;
    question: string;
    similarity: number;
  }[];
}

export interface Stats {
  open: number;
  resolved: number;
  total: number;
  no_context: number;
  out_of_scope: number;
  top_gaps: {
    gap_id: string;
    query: string;
    count: number;
  }[];
}

export type JobType = 'crawl' | 'pdf_index' | 'faq_index' | 'text_index';

export interface SourceJob {
  job_id: string;
  source_id: string;
  job_type: JobType;
  status: 'queued' | 'running' | 'done' | 'failed';
  chunks_created: number;
  embedding_errors: number;
  started_at?: string;
  finished_at?: string;
  error?: string;
  config?: Record<string, any>;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ModelUsage {
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
  avg_latency_ms: number;
  success_count: number;
  error_count: number;
  cost: number;
}

export interface PlatformOverview {
  total_tenants: number;
  active_tenants: number;
  total_conversations: number;
  total_messages: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost: number;
  model_usage: ModelUsage[];
  avg_latency_ms: number;
  success_count: number;
  error_count: number;
  error_rate: number;
  total_leads: number;
  lead_conversion: number;
  like_count: number;
  dislike_count: number;
  like_ratio: number;
}

export interface TimeSeriesPoint {
  date: string;
  messages: number;
  conversations: number;
  tokens: number;
  cost: number;
  leads: number;
}

export interface TenantUsage {
  tenant_id: string;
  domain: string;
  business_name: string;
  plan: string;
  created_at: string;
  conversations: number;
  visitors: number;
  messages: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  model_usage: ModelUsage[];
  leads: number;
  likes: number;
  dislikes: number;
  like_ratio: number;
  last_activity: string | null;
}

export interface TenantAnalyticsDetail {
  tenant: {
    tenant_id: string;
    domain: string;
    plan: string;
    business_name: string;
    created_at: string;
  };
  kpi: {
    conversations: number;
    visitors: number;
    messages: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost: number;
    model_usage: ModelUsage[];
    avg_latency_ms: number;
    leads: number;
    lead_conversion: number;
    likes: number;
    dislikes: number;
    like_ratio: number;
    last_activity: string | null;
  };
  timeseries: TimeSeriesPoint[];
}
