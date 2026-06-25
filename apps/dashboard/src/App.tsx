import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom';
import { StoreProvider } from './store';
import Layout from './components/Layout';
import { privateAxios, adminAxios } from './utils/axios';

// Pages
import Login from './pages/Login';
import Overview from './pages/Overview';
import Sources from './pages/Sources';
import PDFUpload from './pages/PDFUpload';
import FAQs from './pages/FAQs';
import TextDocs from './pages/TextDocs';
import Crawl from './pages/Crawl';
import History from './pages/History';
import KnowledgeImprovement from './pages/KnowledgeImprovement';
import Leads from './pages/Leads';
import Settings from './pages/Settings';
import AdminLogin from './pages/AdminLogin';
import AdminTenants from './pages/AdminTenants';

// System Admin Layout Component
import { Shield, Users, LogOut, Sun, Moon } from 'lucide-react';

const AuthSpinner = () => (
  <div className="flex h-screen items-center justify-center bg-slate-950">
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-violet-500 border-t-transparent" />
  </div>
);

const PrivateRoute = ({ children }: { children: React.ReactNode }) => {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    privateAxios.get('/tenants/me')
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <AuthSpinner />;
  return authenticated ? <Layout>{children}</Layout> : <Navigate to="/login" />;
};

const GuestRoute = ({ children }: { children: React.ReactNode }) => {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    privateAxios.get('/tenants/me')
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <AuthSpinner />;
  return authenticated ? <Navigate to="/" /> : <>{children}</>;
};

const AdminLayout = ({ children }: { children: React.ReactNode }) => {
  const navigate = useNavigate();
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return document.documentElement.classList.contains('light') ? 'light' : 'dark';
  });
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    const fetchPendingCount = async () => {
      try {
        const response = await adminAxios.get('/admin/tenants', {
          params: { page: 1, limit: 1, status: 'pending' }
        });
        setPendingCount(response.data.total);
      } catch (e) {
        // Ignored
      }
    };
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 15000);
    return () => clearInterval(interval);
  }, []);

  React.useEffect(() => {
    document.title = "System Admin Dashboard";
  }, []);

  const handleLogout = async () => {
    try {
      await adminAxios.post('/admin/logout');
    } catch {
      // Cookie may already be cleared
    }
    navigate('/admin/login');
  };

  const toggleTheme = () => {
    if (theme === 'light') {
      document.documentElement.classList.remove('light');
      localStorage.setItem('theme', 'dark');
      setTheme('dark');
    } else {
      document.documentElement.classList.add('light');
      localStorage.setItem('theme', 'light');
      setTheme('light');
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Admin Sidebar */}
      <aside className="w-64 border-r border-slate-800 bg-slate-900 px-6 py-6 flex flex-col">
        <div className="flex items-center gap-3 mb-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-white shadow-lg shadow-violet-500/20">
            <Shield size={20} />
          </div>
          <div>
            <span className="font-bold text-slate-100 text-md leading-tight block">System Admin</span>
            <span className="text-xs text-violet-400 font-semibold uppercase tracking-wider">Control Panel</span>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          <Link 
            to="/admin/tenants" 
            className="flex items-center justify-between px-4 py-3 rounded-xl text-sm font-semibold transition-all bg-violet-950/40 text-violet-400 shadow-sm border border-violet-900/40 hover:bg-violet-950/60"
          >
            <div className="flex items-center gap-3">
              <Users size={18} />
              <span>Tenant Management</span>
            </div>
            {pendingCount > 0 && (
              <span className="inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xxs font-bold min-w-5 h-5 bg-rose-600 text-white animate-pulse">
                {pendingCount}
              </span>
            )}
          </Link>
        </nav>

        <div className="border-t border-slate-800 pt-5">
          <button 
            onClick={handleLogout}
            className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold text-rose-400 hover:bg-rose-955/20 hover:text-rose-500 transition-all cursor-pointer"
          >
            <LogOut size={18} />
            <span>Admin Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-900 px-8">
          <h1 className="text-xl font-bold text-white tracking-tight">System Admin Panel</h1>
          <button
            onClick={toggleTheme}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-all duration-200 cursor-pointer"
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
          >
            {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
          </button>
        </header>
        <main className="flex-1 overflow-y-auto p-8">
          <div className="mx-auto max-w-7xl animate-fadeIn">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

const AdminRoute = ({ children }: { children: React.ReactNode }) => {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    adminAxios.get('/admin/me')
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <AuthSpinner />;
  return authenticated ? <AdminLayout>{children}</AdminLayout> : <Navigate to="/admin/login" />;
};

const AdminGuestRoute = ({ children }: { children: React.ReactNode }) => {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    adminAxios.get('/admin/me')
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <AuthSpinner />;
  return authenticated ? <Navigate to="/admin/tenants" /> : <>{children}</>;
};

const App = () => {
  return (
    <StoreProvider>
      <BrowserRouter basename="/dashboard">
        <Routes>
          <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
          <Route path="/" element={<PrivateRoute><Overview /></PrivateRoute>} />
          <Route path="/sources" element={<PrivateRoute><Sources /></PrivateRoute>} />
          <Route path="/sources/pdf" element={<PrivateRoute><PDFUpload /></PrivateRoute>} />
          <Route path="/sources/faqs/:sourceId" element={<PrivateRoute><FAQs /></PrivateRoute>} />
          <Route path="/sources/docs/:sourceId" element={<PrivateRoute><TextDocs /></PrivateRoute>} />
          <Route path="/crawl" element={<PrivateRoute><Crawl /></PrivateRoute>} />
          <Route path="/history" element={<PrivateRoute><History /></PrivateRoute>} />
          <Route path="/knowledge" element={<PrivateRoute><KnowledgeImprovement /></PrivateRoute>} />
          <Route path="/leads" element={<PrivateRoute><Leads /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><Settings /></PrivateRoute>} />
          <Route path="/admin/login" element={<AdminGuestRoute><AdminLogin /></AdminGuestRoute>} />
          <Route path="/admin/tenants" element={<AdminRoute><AdminTenants /></AdminRoute>} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </BrowserRouter>
    </StoreProvider>
  );
};

export default App;
