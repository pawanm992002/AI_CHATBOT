import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { publicAxios } from '../utils/axios';
import { Bot, AlertCircle, Eye, EyeOff, CheckCircle } from 'lucide-react';

const Login = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [domain, setDomain] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [businessName, setBusinessName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = isRegister ? "Register - EduChat AI" : "Login - EduChat AI";
  }, [isRegister]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    const endpoint = isRegister ? '/tenants/register' : '/tenants/login';

    try {
      const payload: any = { domain, password };
      if (isRegister) {
        payload.business_name = businessName;
        payload.email = email;
      }
      const response = await publicAxios.post(endpoint, payload);
      
      if (isRegister) {
        setSuccess(response.data.message || 'Registration successful! Your account is pending administrator approval.');
        setIsRegister(false);
        setDomain('');
        setPassword('');
        setBusinessName('');
        setEmail('');
      } else {
        navigate('/');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8 font-sans text-slate-100">
      <div className="w-full max-w-md space-y-8 animate-fadeIn">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 text-white shadow-lg shadow-violet-900/30">
            <Bot size={28} />
          </div>
          <h2 className="mt-6 text-3xl font-extrabold tracking-tight text-white">
            {isRegister ? 'Create Account' : 'Welcome Back'}
          </h2>
          <p className="mt-2 text-sm text-slate-400 font-medium">
            {isRegister ? 'Set up your chatbot dashboard' : 'Sign in to your chatbot console'}
          </p>
        </div>

        <div className="bg-slate-900 px-8 py-10 shadow-xl rounded-3xl border border-slate-800/80">
          {success && (
            <div className="mb-6 flex items-start gap-3 rounded-xl bg-emerald-950/20 p-4 text-sm text-emerald-350 border border-emerald-900/60 animate-fadeIn">
              <CheckCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {error && (
            <div className="mb-6 flex items-start gap-3 rounded-xl bg-rose-950/20 p-4 text-sm text-rose-350 border border-rose-900/60 animate-fadeIn">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-6" onSubmit={handleSubmit}>
            {isRegister && (
              <>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Business Name
                  </label>
                  <input
                    type="text"
                    placeholder="Your Company Name"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    required
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all duration-200 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all duration-200 text-sm"
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Domain name
              </label>
              <input
                type="text"
                placeholder="example.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                required
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all duration-200 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 pl-4 pr-10 py-3 text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all duration-200 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 cursor-pointer"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-violet-600 py-3.5 text-sm font-semibold text-white shadow-md shadow-violet-900/30 hover:bg-violet-700 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Authenticating...' : isRegister ? 'Create Account' : 'Sign In'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm">
            <span className="text-slate-400 font-medium">
              {isRegister ? 'Already have an account? ' : "Don't have an account? "}
            </span>
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister);
                setError('');
                setSuccess('');
              }}
              className="font-bold text-violet-400 hover:text-violet-300 hover:underline cursor-pointer"
            >
              {isRegister ? 'Sign in' : 'Register'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;