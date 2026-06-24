import { useState, useEffect } from 'react';

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const ua = navigator.userAgent || '';
    const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|mobile|CREW/i;
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    const mqMobile = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
    const isSmallScreen = window.innerWidth <= 768;
    return mobileRegex.test(ua) || (isTouchDevice && mqMobile) || (isTouchDevice && isSmallScreen);
  });

  useEffect(() => {
    const check = () => {
      const ua = navigator.userAgent || '';
      const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|mobile|CREW/i;
      const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
      const mqMobile = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
      const isSmallScreen = window.innerWidth <= 768;
      setIsMobile(mobileRegex.test(ua) || (isTouchDevice && mqMobile) || (isTouchDevice && isSmallScreen));
    };
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  return isMobile;
}
