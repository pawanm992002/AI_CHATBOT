import { useState, useEffect, useRef } from 'react';
import { adminAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { Tenant, PaginatedResponse } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import { 
  Trash2, 
  ShieldAlert, 
  Search, 
  Check, 
  X, 
  Play, 
  Pause, 
  Copy, 
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff
} from 'lucide-react';

const AdminTenants = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Search & Pagination States
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [totalPending, setTotalPending] = useState(0);

  // Micro-interaction states
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [revealKeyId, setRevealKeyId] = useState<string | null>(null);
  const [tenantToDelete, setTenantToDelete] = useState<Tenant | null>(null);
  const [deleteInput, setDeleteInput] = useState('');
  
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchTenants = async (currentPage = page, currentSearch = search, currentLimit = limit, currentStatus = statusFilter) => {
    try {
      setLoading(true);
      const response = await adminAxios.get<PaginatedResponse<Tenant>>('/admin/tenants', {
        params: {
          page: currentPage,
          limit: currentLimit,
          search: currentSearch || undefined,
          status: currentStatus || undefined
        }
      });
      setTenants(response.data.items);
      setTotal(response.data.total);
      setTotalPages(response.data.total_pages);

      // Fetch pending count separately to display request notifications/banners
      const pendingRes = await adminAxios.get<PaginatedResponse<Tenant>>('/admin/tenants', {
        params: { page: 1, limit: 1, status: 'pending' }
      });
      setTotalPending(pendingRes.data.total);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch tenants');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenants(page, search, limit, statusFilter);
  }, [page, limit, statusFilter]);

  // Debounced search handler
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearch(value);
    setPage(1); // Reset to first page on search

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    searchTimeoutRef.current = setTimeout(() => {
      fetchTenants(1, value, limit, statusFilter);
    }, 400);
  };

  const handleStatusFilterChange = (status: string | null) => {
    setStatusFilter(status);
    setPage(1);
  };

  const handleStatusChange = async (tenantId: string, action: 'approve' | 'reject' | 'enable' | 'disable') => {
    try {
      const response = await adminAxios.post(`/admin/tenants/${tenantId}/${action}`);
      const updatedApiKey = response.data.api_key;
      
      // Update tenant list state locally
      setTenants(prev => prev.map(t => {
        if (t.tenant_id === tenantId) {
          const newStatus = (action === 'approve' || action === 'enable') 
            ? 'approved' 
            : action === 'reject' 
              ? 'rejected' 
              : 'disabled';
          
          return { 
            ...t, 
            status: newStatus,
            api_key: updatedApiKey || t.api_key
          };
        }
        return t;
      }));
    } catch (err: any) {
      alert(`Error during ${action}: ` + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (tenantId: string) => {
    try {
      await adminAxios.delete(`/admin/tenants/${tenantId}`);
      fetchTenants(page, search, limit);
    } catch (err: any) {
      alert('Error deleting tenant: ' + (err.response?.data?.detail || err.message));
    }
  };

  const copyToClipboard = (tenantId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(tenantId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getStatusBadge = (status?: string) => {
    const s = status || 'pending';
    switch (s) {
      case 'approved':
        return (
          <span className="inline-flex items-center rounded-full bg-emerald-950/60 px-3 py-1 text-xs font-semibold text-emerald-400 border border-emerald-900/60 shadow-sm shadow-emerald-900/10">
            Active
          </span>
        );
      case 'disabled':
        return (
          <span className="inline-flex items-center rounded-full bg-rose-950/60 px-3 py-1 text-xs font-semibold text-rose-400 border border-rose-900/60 shadow-sm shadow-rose-900/10">
            Disabled
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center rounded-full bg-slate-800/80 px-3 py-1 text-xs font-semibold text-slate-400 border border-slate-700/60">
            Rejected
          </span>
        );
      case 'pending':
      default:
        return (
          <span className="inline-flex items-center rounded-full bg-amber-950/60 px-3 py-1 text-xs font-semibold text-amber-400 border border-amber-900/60 shadow-sm shadow-amber-900/10 animate-pulse">
            Pending
          </span>
        );
    }
  };

  if (loading && tenants.length === 0) {
    return <LoadingSpinner message="Loading tenants..." />;
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-xl bg-rose-950/40 p-6 text-rose-400 border border-rose-900/60 max-w-2xl mx-auto mt-8">
        <ShieldAlert size={24} className="flex-shrink-0" />
        <div>
          <h3 className="font-bold text-white">System Error</h3>
          <p className="text-sm mt-0.5">{error}</p>
          <button 
            onClick={() => { setError(''); fetchTenants(1, '', limit); }}
            className="mt-3 text-xs font-bold text-violet-400 hover:text-violet-300 hover:underline cursor-pointer"
          >
            Retry Fetch
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">System Tenant Console</h2>
          <p className="text-sm text-slate-400 mt-1">Audit registrations, configure keys, approve, and enable/disable tenants.</p>
        </div>
        
        {/* Modern Search bar */}
        <div className="relative w-full md:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <input
            type="text"
            placeholder="Search name, email, domain..."
            value={search}
            onChange={handleSearchChange}
            className="w-full rounded-xl border border-slate-800 bg-slate-900/40 pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:border-violet-600 focus:outline-none transition-all duration-200"
          />
        </div>
      </div>

      {totalPending > 0 && statusFilter !== 'pending' && (
        <div className="flex items-center justify-between gap-3 rounded-xl bg-rose-955/20 text-rose-400 border border-rose-900/30 p-4 text-sm animate-fadeIn">
          <div className="flex items-center gap-3">
            <span className="flex h-2.5 w-2.5 rounded-full bg-rose-500 animate-ping shrink-0" />
            <span>You have <strong className="text-white font-bold">{totalPending}</strong> pending registration request(s) awaiting approval.</span>
          </div>
          <button 
            onClick={() => handleStatusFilterChange('pending')}
            className="text-xs font-bold text-rose-405 hover:text-rose-350 hover:underline cursor-pointer transition-all shrink-0"
          >
            Review Requests
          </button>
        </div>
      )}

      {/* Tab Filters */}
      <div className="flex gap-2 border-b border-slate-800/80 pb-px">
        {[
          { label: 'All', value: null },
          { label: 'Pending Requests', value: 'pending', count: totalPending },
          { label: 'Active', value: 'approved' },
          { label: 'Disabled', value: 'disabled' },
          { label: 'Rejected', value: 'rejected' },
        ].map((tab) => {
          const isSelected = statusFilter === tab.value;
          return (
            <button
              key={tab.label}
              onClick={() => handleStatusFilterChange(tab.value)}
              className={`px-4 py-2.5 text-xs font-bold border-b-2 -mb-px transition-all cursor-pointer flex items-center gap-2 ${
                isSelected
                  ? 'border-violet-500 text-violet-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>{tab.label}</span>
              {tab.count !== undefined && tab.count > 0 && (
                <span className={`inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-xxs font-bold min-w-4 h-4 ${
                  isSelected ? 'bg-violet-600 text-white animate-pulse' : 'bg-rose-955/20 text-rose-455 border border-rose-900/30'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950 shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800/60 text-slate-400 text-xs font-semibold uppercase tracking-wider bg-slate-900/30">
                <th className="px-6 py-4.5">Tenant Details</th>
                <th className="px-6 py-4.5">Status</th>
                <th className="px-6 py-4.5">Plan</th>
                <th className="px-6 py-4.5">API Key Access</th>
                <th className="px-6 py-4.5">Created At</th>
                <th className="px-6 py-4.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-850 text-slate-300">
              {tenants.map((tenant) => {
                const isPending = !tenant.status || tenant.status === 'pending';
                const isApproved = tenant.status === 'approved';
                const isDisabled = tenant.status === 'disabled';
                const isRejected = tenant.status === 'rejected';
                const hasApiKey = tenant.api_key && !tenant.api_key.startsWith('pending_');

                return (
                  <tr key={tenant.tenant_id} className="hover:bg-slate-900/10 transition-colors">
                    <td className="px-6 py-4.5">
                      <div className="flex flex-col">
                        <span className="font-bold text-white text-sm">{tenant.business_name || 'N/A'}</span>
                        <span className="text-xs text-slate-400 mt-0.5">{tenant.email}</span>
                        <span className="text-xs text-purple-400 font-mono mt-1 select-all">{tenant.domain}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4.5">
                      {getStatusBadge(tenant.status)}
                    </td>
                    <td className="px-6 py-4.5">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
                        tenant.plan === 'pro' 
                          ? 'bg-purple-900/30 text-purple-400 border border-purple-800/40' 
                          : 'bg-slate-800 text-slate-400 border border-slate-700/20'
                      }`}>
                        {tenant.plan || 'free'}
                      </span>
                    </td>
                    <td className="px-6 py-4.5">
                      {hasApiKey ? (
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-400 bg-slate-900/60 px-2 py-1.5 rounded-lg border border-slate-800/80">
                            {revealKeyId === tenant.tenant_id 
                              ? tenant.api_key 
                              : `sk_live_••••••••••••••••••••••••`
                            }
                          </span>
                          <button
                            onClick={() => setRevealKeyId(prev => prev === tenant.tenant_id ? null : tenant.tenant_id)}
                            className="text-slate-500 hover:text-slate-300 p-1 transition-colors rounded hover:bg-slate-900 cursor-pointer"
                            title={revealKeyId === tenant.tenant_id ? "Hide API Key" : "Show API Key"}
                          >
                            {revealKeyId === tenant.tenant_id ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                          <button
                            onClick={() => copyToClipboard(tenant.tenant_id, tenant.api_key || '')}
                            className="text-slate-500 hover:text-slate-350 p-1 transition-colors rounded hover:bg-slate-900 cursor-pointer"
                            title="Copy API Key"
                          >
                            {copiedId === tenant.tenant_id ? (
                              <CheckCheck size={14} className="text-emerald-400 animate-pulse" />
                            ) : (
                              <Copy size={14} />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-550 font-medium italic">
                          Generated on approval
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4.5 text-slate-400 text-sm">
                      {formatDate(tenant.created_at)}
                    </td>
                    <td className="px-6 py-4.5 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        {/* Approve Button */}
                        {(isPending || isRejected) && (
                          <button
                            onClick={() => handleStatusChange(tenant.tenant_id, 'approve')}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-950/20 text-emerald-500 border border-emerald-900/30 hover:bg-emerald-900/40 hover:text-emerald-350 transition-all cursor-pointer"
                            title="Approve Tenant"
                          >
                            <Check size={15} />
                          </button>
                        )}

                        {/* Reject Button */}
                        {isPending && (
                          <button
                            onClick={() => handleStatusChange(tenant.tenant_id, 'reject')}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-rose-950/20 text-rose-500 border border-rose-900/30 hover:bg-rose-900/40 hover:text-rose-350 transition-all cursor-pointer"
                            title="Reject Tenant"
                          >
                            <X size={15} />
                          </button>
                        )}

                        {/* Disable Toggle */}
                        {isApproved && (
                          <button
                            onClick={() => handleStatusChange(tenant.tenant_id, 'disable')}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-amber-950/20 text-amber-500 border border-amber-900/30 hover:bg-amber-900/40 hover:text-amber-350 transition-all cursor-pointer"
                            title="Disable Tenant"
                          >
                            <Pause size={14} />
                          </button>
                        )}

                        {/* Enable Toggle */}
                        {isDisabled && (
                          <button
                            onClick={() => handleStatusChange(tenant.tenant_id, 'enable')}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-950/20 text-emerald-500 border border-emerald-900/30 hover:bg-emerald-900/40 hover:text-emerald-350 transition-all cursor-pointer"
                            title="Enable Tenant"
                          >
                            <Play size={14} />
                          </button>
                        )}

                        <div className="w-px h-5 bg-slate-800 mx-1" />

                        {/* Delete Button */}
                        <button
                          onClick={() => {
                            setTenantToDelete(tenant);
                            setDeleteInput('');
                          }}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 border border-transparent hover:bg-rose-950/30 hover:text-rose-450 hover:border-rose-900/20 transition-all cursor-pointer"
                          title="Delete Tenant"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {tenants.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-slate-500 font-medium">
                    No tenants match the search filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Premium Pagination controls */}
        {total > 0 && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-900 bg-slate-950 px-6 py-4">
            <div className="text-xs text-slate-500 font-medium">
              Showing <span className="font-semibold text-slate-350">{(page - 1) * limit + 1}</span> to{' '}
              <span className="font-semibold text-slate-350">{Math.min(page * limit, total)}</span> of{' '}
              <span className="font-semibold text-slate-350">{total}</span> tenants
            </div>

            <div className="flex items-center gap-4">
              {/* Limit dropdown */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-medium">Show</span>
                <select
                  value={limit}
                  onChange={(e) => {
                    const l = parseInt(e.target.value);
                    setLimit(l);
                    setPage(1);
                  }}
                  className="rounded-lg border border-slate-800 bg-slate-900 text-xs text-slate-300 px-2 py-1 focus:outline-none focus:border-violet-600 transition-colors"
                >
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
                <span className="text-xs text-slate-500 font-medium">per page</span>
              </div>

              {/* Prev/Next Buttons */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-850 text-slate-400 hover:bg-slate-900/60 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
                >
                  <ChevronLeft size={16} />
                </button>
                
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                      p === page
                        ? 'bg-violet-600 text-white shadow-md shadow-violet-900/20'
                        : 'border border-transparent text-slate-400 hover:bg-slate-900/40 hover:text-slate-200'
                    }`}
                  >
                    {p}
                  </button>
                ))}

                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-850 text-slate-400 hover:bg-slate-900/60 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {tenantToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-955/80 dark:bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="relative w-full max-w-md bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-2xl animate-scaleUp">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-950/40 text-rose-500 border border-rose-900/30">
                <ShieldAlert size={20} />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-white leading-6">Delete Tenant Account?</h3>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                  This will permanently delete the tenant <strong className="text-white font-semibold">{tenantToDelete.business_name}</strong> ({tenantToDelete.domain}) and all associated knowledge base, leads, crawl jobs, and visitors. This action is irreversible.
                </p>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  Confirm Domain
                </label>
                <p className="text-xs text-slate-450 mb-2">
                  Please type <code className="text-rose-450 font-mono bg-rose-950/30 px-1.5 py-0.5 rounded border border-rose-900/30">delete {tenantToDelete.domain}</code> to confirm.
                </p>
                <input
                  type="text"
                  placeholder={`delete ${tenantToDelete.domain}`}
                  value={deleteInput}
                  onChange={(e) => setDeleteInput(e.target.value)}
                  className="w-full rounded-xl border border-slate-850 dark:border-slate-800 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-650 focus:border-rose-600 focus:outline-none transition-all duration-200 text-sm font-mono"
                  autoFocus
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setTenantToDelete(null)}
                  className="rounded-xl border border-slate-850 px-4 py-2.5 text-xs font-semibold text-slate-400 hover:bg-slate-900 hover:text-slate-250 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteInput !== `delete ${tenantToDelete.domain}`}
                  onClick={async () => {
                    await handleDelete(tenantToDelete.tenant_id);
                    setTenantToDelete(null);
                  }}
                  className="rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md shadow-rose-900/20 hover:bg-rose-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer"
                >
                  Permanently Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminTenants;
