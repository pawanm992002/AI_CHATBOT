import { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, ExternalLink } from 'lucide-react';
import { Tenant, PaginatedResponse } from '../../interfaces';
import { adminAxios } from '../../utils/axios';

interface TenantSelectorProps {
  placeholder?: string;
  className?: string;
}

function TenantSelector({ placeholder = 'Jump to tenant...', className = '' }: TenantSelectorProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Tenant[]>([]);
  const [searching, setSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [focused, setFocused] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTenants = useCallback(async (search?: string) => {
    setSearching(true);
    setShowDropdown(true);
    try {
      const res = await adminAxios.get<PaginatedResponse<Tenant>>('/admin/tenants', {
        params: { search: search || undefined, limit: 8, page: 1 },
      });
      setResults(res.data.items);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  const onInputChange = useCallback((q: string) => {
    setQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.trim().length === 0) {
      fetchTenants();
      return;
    }
    setSearching(true);
    setShowDropdown(true);
    debounceRef.current = setTimeout(() => {
      fetchTenants(q.trim());
    }, 300);
  }, [fetchTenants]);

  const onFocus = useCallback(() => {
    setFocused(true);
    setShowDropdown(true);
    if (query.trim().length === 0) {
      fetchTenants();
    } else {
      setShowDropdown(true);
    }
  }, [query, fetchTenants]);

  const goToTenant = (tenantId: string) => {
    setShowDropdown(false);
    setQuery('');
    setResults([]);
    navigate(`/admin/analytics/${tenantId}`);
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
        setFocused(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={wrapperRef} className={`relative ${className}`}>
      <div className={`relative rounded-xl border transition-colors ${
        focused
          ? 'border-violet-600/60 ring-1 ring-violet-600/30'
          : 'border-slate-800/80 hover:border-slate-700/60'
      }`}>
        <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          type="text"
          value={query}
          onChange={(e) => onInputChange(e.target.value)}
          onFocus={onFocus}
          placeholder={placeholder}
          className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-slate-900 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none transition-colors"
        />
        <div className="absolute right-3.5 top-1/2 -translate-y-1/2">
          {searching && (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-transparent" />
          )}
        </div>
      </div>

      {showDropdown && results.length > 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-xl bg-slate-900 border border-slate-800/80 shadow-2xl overflow-hidden">
          {results.map((t) => (
            <button
              key={t.tenant_id}
              onClick={() => goToTenant(t.tenant_id)}
              className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/40 transition-colors cursor-pointer group"
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white truncate group-hover:text-violet-300 transition-colors">
                  {t.business_name || t.domain}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-500 truncate">
                  <span>{t.domain}</span>
                  {t.plan && t.plan !== 'free' && (
                    <span className="inline-flex items-center rounded-full px-1.5 py-0 text-[10px] font-semibold uppercase bg-purple-900/30 text-purple-400 border border-purple-800/40">
                      {t.plan}
                    </span>
                  )}
                  {t.email && (
                    <span className="text-slate-600">{t.email}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-3">
                <ExternalLink size={14} className="text-slate-600 group-hover:text-violet-400 transition-colors" />
              </div>
            </button>
          ))}
        </div>
      )}

      {showDropdown && !searching && results.length === 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-xl bg-slate-900 border border-slate-800/80 shadow-2xl p-4 text-center text-sm text-slate-500">
          No tenants found.
        </div>
      )}
    </div>
  );
}

export default TenantSelector;
