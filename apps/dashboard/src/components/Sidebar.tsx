import { Link, useLocation, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Database, 
  RefreshCw, 
  AlertCircle, 
  Users, 
  Settings, 
  LogOut,
  X,
  Bot,
  Clock,
  Brain,
  Tag,
} from 'lucide-react';
import { publicAxios } from '../utils/axios';
import { useStore } from '../store';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar = ({ isOpen, onClose }: SidebarProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { state, dispatch } = useStore();

  const handleLogout = async () => {
    try { await publicAxios.post('/tenants/logout'); } catch {}
    dispatch({ type: 'RESET_STORE' });
    navigate('/login');
  };

  const navItems = [
    { label: 'Overview', icon: LayoutDashboard, path: '/' },
    { label: 'Sources', icon: Database, path: '/sources' },
    { label: 'Crawl Jobs', icon: RefreshCw, path: '/crawl' },
    { label: 'Index History', icon: Clock, path: '/history' },
    { 
      label: 'Knowledge Gaps', 
      icon: AlertCircle, 
      path: '/knowledge',
      badge: state.gapsCount > 0 ? state.gapsCount : undefined 
    },
    { label: 'Leads', icon: Users, path: '/leads' },
    { label: 'AI Provider', icon: Brain, path: '/ai-provider' },
    { label: 'Visitor Profiles', icon: Tag, path: '/visitor-profiles' },
    { label: 'Settings', icon: Settings, path: '/settings' },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm transition-opacity lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar container */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-slate-800/80 bg-slate-900 px-6 py-6 transition-transform duration-300 ease-in-out lg:translate-x-0
        ${isOpen ? 'translate-x-0' : '-translate-x-0 -translate-x-full lg:static lg:flex'}
      `}>
        {/* Brand Header */}
        <div className="flex items-center justify-between mb-8">
          <Link to="/" className="flex items-center gap-3" onClick={onClose}>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-white shadow-lg shadow-violet-500/20">
              <Bot size={22} className="animate-pulse" />
            </div>
            <div>
              <span className="font-bold text-slate-100 text-lg leading-tight block">EduChat AI</span>
              <span className="text-xs text-slate-400 font-medium">Dashboard</span>
            </div>
          </Link>
          <button 
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800 hover:text-white lg:hidden"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.path === '/' 
              ? location.pathname === '/' 
              : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={onClose}
                className={`
                  flex items-center justify-between px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 group
                  ${active 
                    ? 'bg-violet-950/40 text-violet-400 shadow-sm border border-violet-900/40' 
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}
                `}
              >
                <div className="flex items-center gap-3">
                  <Icon 
                    size={18} 
                    className={`transition-colors duration-200 ${active ? 'text-violet-400' : 'text-slate-500 group-hover:text-slate-350'}`} 
                  />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && (
                  <span className={`
                    inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xxs font-bold min-w-5 h-5
                    ${active ? 'bg-violet-600 text-white' : 'bg-rose-955/20 text-rose-400 border border-rose-900/30'}
                  `}>
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer Area: Role Switcher & User LogOut */}
        <div className="mt-auto space-y-4 pt-5 border-t border-slate-800">


          {/* User profile logout chip */}
          <div className="flex items-center justify-between rounded-xl bg-slate-950 border border-slate-850 p-3.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-950 text-violet-400 font-bold text-sm">
                {state.role ? state.role.substring(0, 2).toUpperCase() : 'AD'}
              </div>
              <div>
                <div className="text-sm font-bold text-slate-200 leading-tight">Admin User</div>
                <div className="text-xxs text-slate-400 font-semibold uppercase tracking-wider mt-0.5">
                  {state.role}
                </div>
              </div>
            </div>
            <button 
              onClick={handleLogout}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-800 hover:text-rose-400 transition-all cursor-pointer"
              title="Logout"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
