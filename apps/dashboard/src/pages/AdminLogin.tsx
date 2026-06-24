import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { publicAxios } from '../utils/axios';
import { Shield, AlertCircle } from 'lucide-react';

const AdminLogin = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "System Admin Login";
  }, []);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await publicAxios.post('/admin/login', { username, password });
      navigate('/admin/tenants');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-purple-600 text-white shadow-lg shadow-purple-500/20">
            <Shield size={26} />
          </div>
          <h2 className="mt-6 text-3xl font-extrabold tracking-tight text-white">
            System Admin Login
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Authenticate to access system-wide control panel
          </p>
        </div>

        <div className="bg-slate-900 border border-slate-800 px-8 py-10 shadow-2xl rounded-3xl">
          {error && (
            <div className="mb-6 flex items-start gap-3 rounded-xl bg-rose-950/40 p-4 text-sm text-rose-400 border border-rose-900/60">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Admin Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-white placeholder-slate-600 focus:border-purple-600 focus:ring-2 focus:ring-purple-600/10 focus:outline-none transition-all duration-200"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-white placeholder-slate-600 focus:border-purple-600 focus:ring-2 focus:ring-purple-600/10 focus:outline-none transition-all duration-200"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-purple-600 py-3.5 text-sm font-semibold text-white shadow-md shadow-purple-500/20 hover:bg-purple-700 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Entering Panel...' : 'Enter Dashboard'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AdminLogin;
