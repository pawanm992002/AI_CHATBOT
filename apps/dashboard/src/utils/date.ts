export const formatDate = (dt: string | null | undefined): string => {
  if (!dt) return '-';
  try {
    return new Date(dt).toLocaleString();
  } catch {
    return '-';
  }
};

export const formatDateOnly = (dt: string | null | undefined): string => {
  if (!dt) return '-';
  try {
    return new Date(dt).toLocaleDateString();
  } catch {
    return '-';
  }
};
