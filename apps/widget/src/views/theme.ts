export const ACCENT_FALLBACK = '#4F46E5';

export function luminance(r: number, g: number, b: number): number {
  const a = [r, g, b].map(v => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
}

export function parseRgb(str: string): [number, number, number] | null {
  const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : null;
}

export function parseOklch(str: string): number | null {
  const m = str.match(/oklch\(([\d.%]+)/);
  if (!m) return null;
  const lightnessStr = m[1];
  if (lightnessStr.endsWith('%')) {
    return parseFloat(lightnessStr) / 100;
  }
  return parseFloat(lightnessStr);
}

export function isColorDark(colorStr: string): boolean {
  if (!colorStr || colorStr === 'transparent' || colorStr === 'rgba(0, 0, 0, 0)') {
    return false;
  }
  
  const str = colorStr.trim().toLowerCase();
  
  // 1. Check for OKLCH
  if (str.startsWith('oklch')) {
    const lightness = parseOklch(str);
    if (lightness !== null) {
      return lightness < 0.45;
    }
  }
  
  // 2. Check for RGB / RGBA
  if (str.startsWith('rgb')) {
    const rgb = parseRgb(str);
    if (rgb) {
      return luminance(rgb[0], rgb[1], rgb[2]) < 0.4;
    }
  }
  
  // 3. Check for HEX
  if (str.startsWith('#')) {
    const hex = str.replace('#', '');
    let r = 0, g = 0, b = 0;
    if (hex.length === 3) {
      r = parseInt(hex[0] + hex[0], 16);
      g = parseInt(hex[1] + hex[1], 16);
      b = parseInt(hex[2] + hex[2], 16);
    } else if (hex.length === 6 || hex.length === 8) {
      r = parseInt(hex.substring(0, 2), 16);
      g = parseInt(hex.substring(2, 4), 16);
      b = parseInt(hex.substring(4, 6), 16);
    }
    return luminance(r, g, b) < 0.4;
  }
  
  return false;
}

export function getPalette(accent: string, isDark: boolean) {
  return {
    containerBg: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.92)',
    containerBorder: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
    headerBg: isDark
      ? `linear-gradient(135deg, ${accent}, ${accent}BB)`
      : `linear-gradient(135deg, ${accent}, ${accent}DD)`,
    headerText: '#fff',
    msgAreaBg: isDark ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.01)',
    userBubbleBg: accent,
    userBubbleText: '#fff',
    assistantBubbleBg: isDark ? 'rgba(255, 255, 255, 0.07)' : '#fff',
    assistantBubbleText: isDark ? '#f1f5f9' : '#0f172a',
    assistantBubbleBorder: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)',
    inputBg: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
    inputBorder: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.08)',
    inputText: isDark ? '#f1f5f9' : '#0f172a',
    inputPlaceholder: isDark ? 'rgba(255, 255, 255, 0.4)' : '#64748b',
    subtleText: isDark ? 'rgba(255, 255, 255, 0.5)' : '#64748b',
    divider: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
    fabShadow: `${accent}40`,
  };
}
export type Palette = ReturnType<typeof getPalette>;
