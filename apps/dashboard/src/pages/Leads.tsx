import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { Lead, LeadFormConfig, LeadFormField } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import {
  Users,
  Mail,
  Phone,
  Calendar,
  MessageSquare,
  Hammer,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  FileText,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { LeadFormBuilder } from '../components/LeadFormBuilder';
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal';

const Leads = () => {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [leadForms, setLeadForms] = useState<LeadFormConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'leads' | 'builder'>('leads');

  const [selectedFormId, setSelectedFormId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LeadFormConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [expandedForms, setExpandedForms] = useState<Set<string>>(new Set());

  const fetchLeads = async () => {
    try {
      const res = await privateAxios.get('/dashboard/leads');
      setLeads(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchLeadForms = async () => {
    try {
      const res = await privateAxios.get('/lead-forms');
      setLeadForms(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchLeads(), fetchLeadForms()]);
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    if (leadForms.length > 0 && expandedForms.size === 0) {
      setExpandedForms(new Set(leadForms.map((f) => f.form_id)));
    }
  }, [leadForms, expandedForms.size]);

  const handleToggleEnabled = async (form: LeadFormConfig) => {
    setTogglingId(form.form_id);
    try {
      await privateAxios.put(`/lead-forms/${form.form_id}`, { enabled: !form.enabled });
      await fetchLeadForms();
    } catch (err) {
      console.error(err);
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await privateAxios.delete(`/lead-forms/${deleteTarget.form_id}`);
      if (selectedFormId === deleteTarget.form_id) {
        setSelectedFormId(null);
      }
      setDeleteTarget(null);
      await fetchLeadForms();
    } catch (err) {
      console.error(err);
    } finally {
      setDeleting(false);
    }
  };

  const handleFormSaved = async (newFormId?: string) => {
    await fetchLeadForms();
    if (newFormId) {
      setSelectedFormId(newFormId);
    }
  };

  const getInitials = (name: string) => {
    return name.split(' ').map((n) => n[0]).join('').substring(0, 2).toUpperCase() || '?';
  };

  const avatarColors = [
    'bg-violet-950/40 text-violet-400 border border-violet-900/30',
    'bg-amber-950/40 text-amber-400 border border-amber-900/30',
    'bg-teal-950/40 text-teal-400 border border-teal-900/30',
    'bg-rose-950/40 text-rose-400 border border-rose-900/30',
    'bg-blue-950/40 text-blue-400 border border-blue-900/30',
  ];

  const groupLeadsByForm = () => {
    const groups: { formId: string | null; form: LeadFormConfig | null; leads: Lead[] }[] = [];
    const formMap = new Map(leadForms.map((f) => [f.form_id, f]));
    const grouped = new Map<string, Lead[]>();

    for (const lead of leads) {
      const key = lead.form_id || '__uncategorized__';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(lead);
    }

    for (const [formId, formLeads] of grouped) {
      if (formId === '__uncategorized__') {
        groups.push({ formId: null, form: null, leads: formLeads });
      } else {
        groups.push({ formId, form: formMap.get(formId) || null, leads: formLeads });
      }
    }

    groups.sort((a, b) => {
      if (!a.form) return 1;
      if (!b.form) return -1;
      return b.leads.length - a.leads.length;
    });

    return groups;
  };

  const getLeadFieldValue = (lead: Lead, field: LeadFormField): string => {
    if (lead.custom_fields && lead.custom_fields[field.field_id]) {
      return lead.custom_fields[field.field_id];
    }
    switch (field.type) {
      case 'email': return lead.email || '-';
      case 'phone': return lead.phone || '-';
      default: return '-';
    }
  };

  const toggleFormExpansion = (key: string) => {
    setExpandedForms((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (loading) {
    return <LoadingSpinner message="Loading leads..." />;
  }

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Leads & Enquiries</h2>
        <p className="text-slate-400 text-sm mt-1">
          Manage lead forms and view contact submissions from website visitors.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800/80 w-fit">
        <button
          onClick={() => setActiveTab('leads')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
            activeTab === 'leads'
              ? 'bg-violet-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Users size={16} />
          View Leads
          {leads.length > 0 && (
            <span className="ml-1 text-xxs bg-white/20 px-1.5 py-0.5 rounded-full">
              {leads.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('builder')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
            activeTab === 'builder'
              ? 'bg-violet-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Hammer size={16} />
          Form Builder
          {leadForms.length > 0 && (
            <span className="ml-1 text-xxs bg-white/20 px-1.5 py-0.5 rounded-full">
              {leadForms.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'leads' ? (
        <div className="space-y-4">
          {leads.length === 0 ? (
            <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg px-6 py-16 text-center max-w-sm mx-auto">
              <Users size={40} className="text-slate-700 mx-auto mb-4 animate-pulse" />
              <h3 className="text-md font-bold text-white">No leads captured</h3>
              <p className="text-xs text-slate-500 mt-2">
                Leads will appear here immediately after a customer fills out the enquiry form in the widget.
                Use the Form Builder tab to configure your lead form.
              </p>
            </div>
          ) : (
            groupLeadsByForm().map(({ formId, form, leads: groupLeads }) => {
              const isExpanded = expandedForms.has(formId || '__uncategorized__');
              const sortedFields = form
                ? [...form.fields].sort((a, b) => a.order - b.order)
                : [];

              return (
                <div key={formId || '__uncategorized__'} className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden">
                  {/* Accordion Header */}
                  <button
                    onClick={() => toggleFormExpansion(formId || '__uncategorized__')}
                    className="w-full flex items-center justify-between px-6 py-4 hover:bg-slate-800/40 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-3">
                      <div className="text-slate-400">
                        {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                      </div>
                      <div className="text-left">
                        <h3 className="text-sm font-bold text-white">
                          {form ? form.title : 'Uncategorized'}
                        </h3>
                        <p className="text-xxs text-slate-500 mt-0.5">
                          {groupLeads.length} lead{groupLeads.length !== 1 ? 's' : ''}
                          {form && ` · ${sortedFields.length} field${sortedFields.length !== 1 ? 's' : ''}`}
                        </p>
                      </div>
                    </div>
                    {form && (
                      <span className={`w-2 h-2 rounded-full ${form.enabled ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                    )}
                  </button>

                  {/* Accordion Content */}
                  {isExpanded && (
                    <div className="overflow-x-auto border-t border-slate-800/80">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-400 text-xxs font-bold uppercase tracking-wider bg-slate-950/60">
                            {form ? (
                              sortedFields.map((field) => (
                                <th key={field.field_id} className="px-6 py-3.5">{field.label}</th>
                              ))
                            ) : (
                              <>
                                <th className="px-6 py-3.5">Contact Name</th>
                                <th className="px-6 py-3.5">Email Address</th>
                                <th className="px-6 py-3.5">Phone Number</th>
                              </>
                            )}
                            <th className="px-6 py-3.5">Message</th>
                            <th className="px-6 py-3.5">Date</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800 text-xs text-slate-300">
                          {groupLeads.map((lead, idx) => {
                            const colorClass = avatarColors[idx % avatarColors.length];
                            return (
                              <tr key={lead.lead_id || idx} className="hover:bg-slate-950/40 transition-colors">
                                {form ? (
                                  sortedFields.map((field) => (
                                    <td key={field.field_id} className="px-6 py-4 text-slate-400 font-medium max-w-[200px] truncate" title={getLeadFieldValue(lead, field)}>
                                      {field.type === 'email' && getLeadFieldValue(lead, field) !== '-' ? (
                                        <span className="flex items-center gap-1.5">
                                          <Mail size={14} className="text-slate-500 flex-shrink-0" />
                                          <span className="truncate">{getLeadFieldValue(lead, field)}</span>
                                        </span>
                                      ) : field.type === 'phone' && getLeadFieldValue(lead, field) !== '-' ? (
                                        <span className="flex items-center gap-1.5">
                                          <Phone size={14} className="text-slate-500 flex-shrink-0" />
                                          <span className="truncate">{getLeadFieldValue(lead, field)}</span>
                                        </span>
                                      ) : (
                                        <span className="truncate">{getLeadFieldValue(lead, field)}</span>
                                      )}
                                    </td>
                                  ))
                                ) : (
                                  <>
                                    <td className="px-6 py-4">
                                      <div className="flex items-center gap-3">
                                        <div className={`h-8 w-8 rounded-full flex items-center justify-center font-bold text-xxs ${colorClass}`}>
                                          {getInitials(lead.name)}
                                        </div>
                                        <span className="font-bold text-white">{lead.name}</span>
                                      </div>
                                    </td>
                                    <td className="px-6 py-4 font-semibold text-slate-400">
                                      <span className="flex items-center gap-1.5">
                                        <Mail size={14} className="text-slate-500" />
                                        {lead.email}
                                      </span>
                                    </td>
                                    <td className="px-6 py-4 text-slate-400 font-medium">
                                      {lead.phone ? (
                                        <span className="flex items-center gap-1.5">
                                          <Phone size={14} className="text-slate-500" />
                                          {lead.phone}
                                        </span>
                                      ) : (
                                        <span className="text-slate-650">-</span>
                                      )}
                                    </td>
                                  </>
                                )}
                                <td className="px-6 py-4 text-slate-400 max-w-xs truncate" title={lead.message}>
                                  <span className="flex items-center gap-1.5">
                                    <MessageSquare size={14} className="text-slate-500 flex-shrink-0" />
                                    <span className="truncate text-wrap">{lead.message || '-'}</span>
                                  </span>
                                </td>
                                <td className="px-6 py-4 text-slate-400">
                                  <span className="flex items-center gap-1.5">
                                    <Calendar size={14} className="text-slate-500" />
                                    {formatDate(lead.created_at)}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      ) : (
        <div className="flex gap-6 min-h-[600px]">
          {/* Sidebar */}
          <div className="w-72 flex-shrink-0 bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-800">
              <button
                onClick={() => setSelectedFormId('new')}
                className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl transition-colors cursor-pointer ${
                  selectedFormId === 'new'
                    ? 'bg-violet-500 text-white shadow-sm'
                    : 'bg-violet-600 text-white hover:bg-violet-700'
                }`}
              >
                <Plus size={16} />
                New Form
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {leadForms.length === 0 ? (
                <div className="py-12 text-center">
                  <FileText size={32} className="text-slate-700 mx-auto mb-3" />
                  <p className="text-xs text-slate-500">No forms yet</p>
                  <p className="text-xxs text-slate-600 mt-1">Click "New Form" to create one</p>
                </div>
              ) : (
                leadForms.map((form) => {
                  const isSelected = selectedFormId === form.form_id;
                  return (
                    <div
                      key={form.form_id}
                      onClick={() => setSelectedFormId(form.form_id)}
                      className={`group relative p-3 rounded-xl cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-violet-600/10 border border-violet-600/30'
                          : 'hover:bg-slate-800/60 border border-transparent'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className={`text-sm font-semibold truncate ${isSelected ? 'text-violet-300' : 'text-slate-200'}`}>
                            {form.title}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xxs text-slate-500">
                              {form.fields.length} field{form.fields.length !== 1 ? 's' : ''}
                            </span>
                            <span className={`w-1.5 h-1.5 rounded-full ${form.enabled ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                          </div>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleEnabled(form);
                            }}
                            disabled={togglingId === form.form_id}
                            className="p-1 cursor-pointer disabled:opacity-50"
                            title={form.enabled ? 'Disable form' : 'Enable form'}
                          >
                            {form.enabled ? (
                              <ToggleRight size={18} className="text-emerald-400" />
                            ) : (
                              <ToggleLeft size={18} className="text-slate-600" />
                            )}
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteTarget(form);
                            }}
                            className="p-1 text-slate-500 hover:text-rose-400 cursor-pointer"
                            title="Delete form"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Editor Panel */}
          <div className="flex-1 min-w-0">
            {selectedFormId ? (
              <LeadFormBuilder
                existingForms={leadForms}
                selectedFormId={selectedFormId}
                onSaved={handleFormSaved}
              />
            ) : (
              <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg h-full flex items-center justify-center">
                <div className="text-center px-6">
                  <FileText size={48} className="text-slate-700 mx-auto mb-4" />
                  <h3 className="text-base font-bold text-white">Select a form to edit</h3>
                  <p className="text-xs text-slate-500 mt-2 max-w-xs mx-auto">
                    Choose a form from the sidebar to edit it, or click "New Form" to create a fresh one.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <DeleteConfirmationModal
          formTitle={deleteTarget.title}
          onConfirm={handleDelete}
          onCancel={() => {
            setDeleteTarget(null);
          }}
          loading={deleting}
        />
      )}
    </div>
  );
};

export default Leads;
