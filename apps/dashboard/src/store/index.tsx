import { createContext, useContext, useReducer, ReactNode } from 'react';
import { Lead, Stats } from '../interfaces';

export type UserRole = 'admin' | 'editor' | 'viewer';

interface State {
  gapsCount: number;
  knowledge_sources: number;
  leads: Lead[];
  stats: Stats | null;
  loading: boolean;
  error: string | null;
  role: UserRole;
}

const initialState: State = {
  gapsCount: 0,
  knowledge_sources: 0,
  leads: [],
  stats: null,
  loading: false,
  error: null,
  role: 'admin',
};

type Action =
  | { type: 'SET_GAPS_COUNT'; payload: number }
  | { type: 'SET_SOURCES'; payload: number }
  | { type: 'SET_LEADS'; payload: Lead[] }
  | { type: 'SET_STATS'; payload: Stats }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_ROLE'; payload: UserRole }
  | { type: 'RESET_STORE' };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_GAPS_COUNT':
      return { ...state, gapsCount: action.payload };
    case 'SET_SOURCES':
      return { ...state, knowledge_sources: action.payload };
    case 'SET_LEADS':
      return { ...state, leads: action.payload };
    case 'SET_STATS':
      return { 
        ...state, 
        stats: action.payload, 
        gapsCount: action.payload.open 
      };
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_ROLE':
      return { ...state, role: action.payload };
    case 'RESET_STORE':
      return {
        ...initialState,
      };
    default:
      return state;
  }
}

const StoreContext = createContext<{
  state: State;
  dispatch: React.Dispatch<Action>;
} | undefined>(undefined);

export const StoreProvider = ({ children }: { children: ReactNode }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  return (
    <StoreContext.Provider value={{ state, dispatch }}>
      {children}
    </StoreContext.Provider>
  );
};

export const useStore = () => {
  const context = useContext(StoreContext);
  if (!context) {
    throw new Error('useStore must be used within a StoreProvider');
  }
  return context;
};

// RBAC permission check helper
export const hasAccess = (role: UserRole, action: 'delete' | 'write' | 'read' | 'rotate') => {
  if (role === 'admin') return true;
  if (role === 'editor') {
    return action === 'write' || action === 'read';
  }
  // viewer has read-only access
  return action === 'read';
};
