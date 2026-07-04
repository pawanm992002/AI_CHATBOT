export const formatDate = (dt: string | null | undefined): string => {
  if (!dt) return '-';
  try {
    return new Date(dt).toLocaleString('en-IN', {
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
    return new Date(dt).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      timeZone: 'Asia/Kolkata',
    });
  } catch {
    return '-';
  }
};
