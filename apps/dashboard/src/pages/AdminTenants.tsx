import { useState, useEffect } from 'react';
import { adminAxios } from '../utils/axios';
import { formatDate } from '../utils/date';
import { Tenant } from '../interfaces';
import { LoadingSpinner } from '@chatbot/shared';
import { Trash2, ShieldAlert } from 'lucide-react';

const AdminTenants = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchTenants = async () => {
    try {
      setLoading(true);
      const response = await adminAxios.get('/admin/tenants');
      setTenants(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch tenants');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenants();
  }, []);

  const handleDelete = async (tenantId: string) => {
    if (!window.confirm('Are you sure you want to delete this tenant? This will delete all their data.')) return;

    try {
      await adminAxios.delete(`/admin/tenants/${tenantId}`);
      setTenants((prev) => prev.filter((t) => t.tenant_id !== tenantId));
    } catch (err: any) {
      alert('Error deleting tenant: ' + (err.response?.data?.detail || err.message));
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading tenants..." />;
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-xl bg-rose-950/40 p-6 text-rose-400 border border-rose-900/60 max-w-2xl mx-auto mt-8">
        <ShieldAlert size={24} className="flex-shrink-0" />
        <div>
          <h3 className="font-bold text-white">System Error</h3>
          <p className="text-sm mt-0.5">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">System Tenants</h2>
        <p className="text-sm text-slate-400 mt-1">Manage all registered tenants in the system.</p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase tracking-wider bg-slate-900/40">
                <th className="px-6 py-4">Domain</th>
                <th className="px-6 py-4">Plan</th>
                <th className="px-6 py-4">Created At</th>
                <th className="px-6 py-4">Tenant ID</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {tenants.map((tenant) => (
                <tr key={tenant.tenant_id} className="hover:bg-slate-900/20 transition-colors">
                  <td className="px-6 py-4 font-semibold text-white">{tenant.domain}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      tenant.plan === 'pro' 
                        ? 'bg-purple-900/30 text-purple-400 border border-purple-800/40' 
                        : 'bg-slate-800 text-slate-400'
                    }`}>
                      {tenant.plan || 'free'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-slate-400 text-sm">
                    {formatDate(tenant.created_at)}
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-slate-500">
                    {tenant.tenant_id}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => handleDelete(tenant.tenant_id)}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-rose-950/40 hover:text-rose-400 transition-colors cursor-pointer"
                      title="Delete Tenant"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-500 font-medium">
                    No tenants found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AdminTenants;
