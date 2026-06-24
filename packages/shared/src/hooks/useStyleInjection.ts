import { useEffect } from 'react';

export function useStyleInjection(): void {
  useEffect(() => {
    const id = 'cw-injected-styles';
    if (document.getElementById(id)) return;

    const style = document.createElement('style');
    style.id = id;
    style.textContent = `
      @keyframes cwPulse {
        0%, 100% { transform: scale(1); box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
        50% { transform: scale(1.05); box-shadow: 0 6px 28px rgba(0,0,0,0.22); }
      }
      @keyframes cwFadeIn {
        from { opacity: 0; transform: translateY(8px) scale(0.97); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }
      @keyframes cwSlideUp {
        from { opacity: 0; transform: translateY(16px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes cwSlideUpMobile {
        from { transform: translateY(100%); }
        to { transform: translateY(0); }
      }
      @keyframes cwBreathe {
        0%, 100% { opacity: 0.25; transform: scale(0.8); }
        50% { opacity: 1; transform: scale(1.1); }
      }
    `;
    document.head.appendChild(style);
  }, []);
}
