export interface Visitor {
  session_id: string;
  tenant_id: string;
  first_seen_at?: string;
  last_seen_at?: string;
  conversation_ids: string[];
  total_messages: number;
  ip_history?: { ip: string; seen_at: string }[];
  page_views?: { url: string; title: string; timestamp: string }[];
  profile_id?: string | null;
  profile_label?: string | null;
  identity?: VisitorIdentity;
  utm_source?: string;
}

export interface VisitorIdentity {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  updated_at?: string | null;
  source_lead_id?: string | null;
}

export interface VisitorProfile {
  id?: string;
  tenant_id?: string;
  name: string;
  description?: string;
  response_instructions?: string;
  color?: string;
  enabled?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Lead {
  lead_id: string;
  name: string;
  email: string;
  phone?: string;
  message: string;
  form_id?: string;
  custom_fields?: Record<string, string>;
  visitor_id?: string;
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
  field_role?: 'name' | 'email' | 'phone' | null;
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
