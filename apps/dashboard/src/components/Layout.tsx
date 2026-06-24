import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { privateAxios } from '../utils/axios';
import { useStore } from '../store';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout = ({ children }: LayoutProps) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { dispatch } = useStore();

  useEffect(() => {
    document.title = 'EduChat AI';
    
    const fetchUserData = async () => {
      try {
        const res = await privateAxios.get('/tenants/me');
        if (res.data && res.data.role) {
          dispatch({ type: 'SET_ROLE', payload: res.data.role });
        }
      } catch (err) {
        console.error('Failed to fetch user role on mount:', err);
      }
    };
    
    fetchUserData();
  }, [dispatch]);

  return (
    <div className="flex min-h-screen bg-slate-950">
      {/* Responsive Sidebar */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main content wrapper */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Topbar header */}
        <Topbar onMenuToggle={() => setSidebarOpen((prev) => !prev)} />

        {/* Content body */}
        <main className="flex-1 overflow-y-auto px-6 py-8 lg:px-8">
          <div className="mx-auto max-w-7xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
