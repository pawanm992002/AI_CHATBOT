import axios from 'axios';

const isLocalhost = Boolean(
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1' ||
  window.location.hostname === '[::1]'
);

export const API_BASE_URL = isLocalhost
  ? ''
  : (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// Public instance for calls that don't need auth (like Login)
// withCredentials needed so browser stores Set-Cookie from login/register responses
export const publicAxios = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Private instance for normal tenant endpoints (JWT sent via HttpOnly cookie)
export const privateAxios = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to handle unauthorized/forbidden responses globally
privateAxios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status } = error.response;
      if (status === 401 || status === 403) {
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/dashboard/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// Admin instance for sys admin endpoints (JWT sent via HttpOnly cookie)
export const adminAxios = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

adminAxios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status } = error.response;
      if (status === 401 || status === 403) {
        if (!window.location.pathname.includes('/admin/login')) {
          window.location.href = '/dashboard/admin/login';
        }
      }
    }
    return Promise.reject(error);
  }
);
