import { useState, useCallback } from 'react';

export const useRbacError = (duration = 4000) => {
  const [rbacError, setRbacError] = useState<string | null>(null);

  const triggerRbacError = useCallback((msg: string) => {
    setRbacError(msg);
    setTimeout(() => setRbacError(null), duration);
  }, [duration]);

  return { rbacError, triggerRbacError };
};
