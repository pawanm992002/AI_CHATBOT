import { useEffect, useState, useCallback } from 'react';
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
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { LeadFormBuilder } from '../components/LeadFormBuilder';
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal';

const PAGE_SIZE = 20;

const avatarColors = [
  'bg-violet-950/40 text-violet-400 border border-violet-900/30',
  'bg-amber-950/40 text-amber-400 border border-amber-900/30',
  'bg-teal-950/40 text-teal-400 border border-teal-900/30',
  'bg-rose-950/40 text-rose-400 border border-rose-900/30',
  'bg-blue-950/40 text-blue-400 border border-blue-900/30',
];

const getInitials = (name: string) => {
  return name.split(' ').map((n) => n[0]).join('').substring(0, 2).toUpperCase() || '?';
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

const Leads = () => {
  const [leadForms, setLeadForms] = useState<LeadFormConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'leads' | 'builder'>('leads');
  const [activeFormTab, setActiveFormTab] = useState('__all__');

  const [selectedFormId, setSelectedFormId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LeadFormConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // Leads table state
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loadingLeads, setLoadingLeads] = useState(false);

  const fetchLeadForms = async () => {
    try {
      const res = await privateAxios.get('/lead-forms');
      setLeadForms(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchLeads = useCallback(async (formTab: string, pageNum: number) => {
    setLoadingLeads(true);
    try {
      const params: Record<string, string | number> = { page: pageNum, page_size: PAGE_SIZE };
      if (formTab !== '__all__' && formTab !== '__uncategorized__') {
        params.form_id = formTab;
      }
      const res = await privateAxios.get('/dashboard/leads', { params });
      let items = res.data.items;

      if (formTab === '__uncategorized__') {
        items = items.filter((l: Lead) => !l.form_id || l.form_id === '');
      }

      setLeads(items);
      setTotal(res.data.total);
      setPage(res.data.page);
      setTotalPages(res.data.total_pages);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingLeads(false);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchLeadForms();
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    fetchLeads(activeFormTab, 1);
  }, [activeFormTab, fetchLeads]);

  const handlePageChange = (newPage: number) => {
    fetchLeads(activeFormTab, newPage);
  };

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

  const activeForm = leadForms.find((f) => f.form_id === activeFormTab);
  const sortedFields = activeForm ? [...activeForm.fields].sort((a, b) => a.order - b.order) : [];

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

      {/* Top-level Tabs */}
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
          {/* Form-level Tabs */}
          <div className="flex gap-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800/50 overflow-x-auto">
            <button
              onClick={() => setActiveFormTab('__all__')}
              className={`flex-shrink-0 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeFormTab === '__all__'
                  ? 'bg-slate-700 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              All
            </button>
            {leadForms.map((form) => (
              <button
                key={form.form_id}
                onClick={() => setActiveFormTab(form.form_id)}
                className={`flex items-center gap-1.5 flex-shrink-0 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  activeFormTab === form.form_id
                    ? 'bg-slate-700 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${form.enabled ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                {form.title}
              </button>
            ))}
            <button
              onClick={() => setActiveFormTab('__uncategorized__')}
              className={`flex-shrink-0 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeFormTab === '__uncategorized__'
                  ? 'bg-slate-700 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              Uncategorized
            </button>
          </div>

          {/* Leads Table */}
          <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden">
            {loadingLeads ? (
              <div className="px-6 py-16 text-center">
                <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto" />
                <p className="text-xs text-slate-500 mt-2">Loading leads...</p>
              </div>
            ) : leads.length === 0 ? (
              <div className="px-6 py-16 text-center max-w-sm mx-auto">
                <Users size={40} className="text-slate-700 mx-auto mb-4 animate-pulse" />
                <h3 className="text-md font-bold text-white">No leads found</h3>
                <p className="text-xs text-slate-500 mt-2">
                  {activeFormTab === '__all__'
                    ? 'Leads will appear here after visitors fill out the enquiry form in the widget.'
                    : activeFormTab === '__uncategorized__'
                    ? 'No leads without an associated form.'
                    : 'No leads submitted through this form yet.'}
                </p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-xxs font-bold uppercase tracking-wider bg-slate-950/60">
                        {activeFormTab !== '__all__' && activeFormTab !== '__uncategorized__' && sortedFields.length > 0 ? (
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
                      {leads.map((lead, idx) => (
                        <tr key={lead.lead_id || idx} className="hover:bg-slate-950/40 transition-colors">
                          {activeFormTab !== '__all__' && activeFormTab !== '__uncategorized__' && sortedFields.length > 0 ? (
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
                                  <div className={`h-8 w-8 rounded-full flex items-center justify-center font-bold text-xxs ${avatarColors[idx % avatarColors.length]}`}>
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
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-6 py-3 border-t border-slate-800/80">
                    <p className="text-xxs text-slate-500">
                      Page {page} of {totalPages} · {total} total
                    </p>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handlePageChange(page - 1)}
                        disabled={page <= 1}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                      >
                        <ChevronLeft size={16} />
                      </button>
                      {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                        let pageNum: number;
                        if (totalPages <= 5) {
                          pageNum = i + 1;
                        } else if (page <= 3) {
                          pageNum = i + 1;
                        } else if (page >= totalPages - 2) {
                          pageNum = totalPages - 4 + i;
                        } else {
                          pageNum = page - 2 + i;
                        }
                        return (
                          <button
                            key={pageNum}
                            onClick={() => handlePageChange(pageNum)}
                            className={`w-7 h-7 rounded-lg text-xxs font-semibold transition-colors cursor-pointer ${
                              pageNum === page
                                ? 'bg-violet-600 text-white'
                                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                            }`}
                          >
                            {pageNum}
                          </button>
                        );
                      })}
                      <button
                        onClick={() => handlePageChange(page + 1)}
                        disabled={page >= totalPages}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
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
