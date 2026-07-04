const toUTCDate = (dt: string): Date => {
  if (dt.endsWith('Z') || dt.includes('+') || /[-+]\d{2}:\d{2}$/.test(dt)) {
    return new Date(dt);
  }
  return new Date(dt + 'Z');
};

export const formatDate = (dt: string | null | undefined): string => {
  if (!dt) return '-';
  try {
    return toUTCDate(dt).toLocaleString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata',
      timeZoneName: 'short',
    });
  } catch {
    return '-';
  }
};

export const formatDateOnly = (dt: string | null | undefined): string => {
  if (!dt) return '-';
  try {
    return toUTCDate(dt).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      timeZone: 'Asia/Kolkata',
    });
  } catch {
    return '-';
  }
};
