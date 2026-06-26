import { useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { Lead, LeadFormConfig } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import { Users, Mail, Phone, Calendar, MessageSquare, Hammer } from 'lucide-react';
import { LeadFormBuilder } from '../components/LeadFormBuilder';

const Leads = () => {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [leadForms, setLeadForms] = useState<LeadFormConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'leads' | 'builder'>('leads');

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
              {leadForms[0]?.enabled ? 'Active' : 'Off'}
            </span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'leads' ? (
        <div className="bg-slate-900 rounded-3xl border border-slate-800/80 shadow-lg overflow-hidden">
          {leads.length === 0 ? (
            <div className="px-6 py-16 text-center max-w-sm mx-auto">
              <Users size={40} className="text-slate-700 mx-auto mb-4 animate-pulse" />
              <h3 className="text-md font-bold text-white">No leads captured</h3>
              <p className="text-xs text-slate-500 mt-2">
                Leads will appear here immediately after a customer fills out the enquiry form in the widget.
                Use the Form Builder tab to configure your lead form.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-xxs font-bold uppercase tracking-wider bg-slate-950/60">
                    <th className="px-6 py-3.5">Contact Name</th>
                    <th className="px-6 py-3.5">Email Address</th>
                    <th className="px-6 py-3.5">Phone Number</th>
                    <th className="px-6 py-3.5">Message Text</th>
                    <th className="px-6 py-3.5">Submission Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-xs text-slate-300">
                  {leads.map((lead, idx) => {
                    const colorClass = avatarColors[idx % avatarColors.length];
                    return (
                      <tr key={lead.lead_id || idx} className="hover:bg-slate-950/40 transition-colors">
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
      ) : (
        <LeadFormBuilder
          existingForms={leadForms}
          onSaved={async () => {
            await fetchLeadForms();
          }}
        />
      )}
    </div>
  );
};

export default Leads;
