import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Menu, User, Bell, Sun, Moon } from 'lucide-react';
import { useStore } from '../store';

interface TopbarProps {
  onMenuToggle: () => void;
}

export const Topbar = ({ onMenuToggle }: TopbarProps) => {
  const location = useLocation();
  const { state } = useStore();
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return document.documentElement.classList.contains('light') ? 'light' : 'dark';
  });

  const getPageTitle = (pathname: string) => {
    if (pathname === '/') return 'Console Overview';
    if (pathname.startsWith('/sources')) return 'Data Sources';
    if (pathname.startsWith('/crawl')) return 'Crawl Jobs';
    if (pathname.startsWith('/knowledge')) return 'Knowledge Gaps';
    if (pathname.startsWith('/leads')) return 'Leads & Enquiries';
    if (pathname.startsWith('/ai-provider')) return 'AI Provider';
    if (pathname.startsWith('/settings')) return 'Settings';
    if (pathname.startsWith('/admin')) return 'System Administration';
    return 'Dashboard';
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
    <header className="flex h-16 items-center justify-between border-b border-slate-800/80 bg-slate-900 px-6 lg:px-8">
      {/* Left side: Hamburger (mobile) + Page Title */}
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuToggle}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-800/60 lg:hidden cursor-pointer"
        >
          <Menu size={20} />
        </button>
        <h1 className="text-lg font-bold text-white tracking-tight sm:text-xl lg:text-2xl">
          {getPageTitle(location.pathname)}
        </h1>
      </div>

      {/* Right side: Notifications & User profile */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleTheme}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-all duration-200 cursor-pointer"
          title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
        >
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <button className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-colors cursor-pointer">
          <Bell size={18} />
        </button>
        <div className="h-6 w-px bg-slate-800" />
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-slate-300">
            <User size={16} />
          </div>
          <div className="hidden sm:flex flex-col text-left">
            <span className="text-xs font-semibold text-slate-200">Admin User</span>
            <span className="text-xxs font-bold text-violet-400 uppercase tracking-wider mt-0.5">{state.role}</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Topbar;
