import { useState, useEffect } from 'react';
import { ThemeState } from '@chatbot/shared';
import { ACCENT_FALLBACK, isColorDark } from '../utils/theme';
import { DEFAULT_FONT_FAMILY } from '../utils/constants';

function checkDarkTheme(): boolean {
  try {
    const htmlEl = document.documentElement;
    const bodyEl = document.body;

    const htmlTheme = htmlEl.getAttribute('data-theme') || htmlEl.getAttribute('data-mode') || '';
    const bodyTheme = bodyEl.getAttribute('data-theme') || bodyEl.getAttribute('data-mode') || '';
    if (htmlTheme.includes('dark') || bodyTheme.includes('dark')) {
      return true;
    }

    const darkClasses = ['dark', 'dark-mode', 'theme-dark', 'night-mode', 'is-dark'];
    for (const cls of darkClasses) {
      if (htmlEl.classList.contains(cls) || bodyEl.classList.contains(cls)) {
        return true;
      }
    }

    const bodyStyles = window.getComputedStyle(bodyEl);
    const docStyles = window.getComputedStyle(htmlEl);
    const bgRaw = bodyStyles.backgroundColor || docStyles.backgroundColor;
    return isColorDark(bgRaw);
  } catch {
    return false;
  }
}

export function useHostTheme(): ThemeState {
  const [theme, setTheme] = useState<ThemeState>({
    accent: ACCENT_FALLBACK,
    font: DEFAULT_FONT_FAMILY,
    isDark: false,
  });

  useEffect(() => {
    const updateTheme = () => {
      try {
        const bodyStyles = window.getComputedStyle(document.body);
        const docEl = document.documentElement;
        const docStyles = window.getComputedStyle(docEl);

        const font = bodyStyles.fontFamily || docStyles.fontFamily || theme.font;

        let accent = ACCENT_FALLBACK;
        const varNames = ['--primary', '--accent', '--main-color', '--brand-color', '--color-primary', '--theme-color'];
        for (const name of varNames) {
          const val = docStyles.getPropertyValue(name).trim() || bodyStyles.getPropertyValue(name).trim();
          if (val && (val.startsWith('#') || val.startsWith('rgb') || val.startsWith('oklch'))) {
            accent = val;
            break;
          }
        }

        const isDark = checkDarkTheme();
        setTheme({ accent, font, isDark });
      } catch {
        // Fallback
      }
    };

    updateTheme();

    const observer = new MutationObserver(() => {
      updateTheme();
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-theme', 'data-mode', 'style'],
    });
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ['class', 'data-theme', 'data-mode', 'style'],
    });

    return () => observer.disconnect();
  }, [theme.font]);

  return theme;
}
