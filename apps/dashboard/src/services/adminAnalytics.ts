import { adminAxios } from '../utils/axios';
import {
  PlatformOverview,
  TimeSeriesPoint,
  TenantUsage,
  PaginatedResponse,
  TenantAnalyticsDetail,
  ModelUsage,
} from '../interfaces';

export async function fetchOverview(): Promise<PlatformOverview> {
  const res = await adminAxios.get<PlatformOverview>('/admin/analytics/overview');
  return res.data;
}

export async function fetchTimeseries(period: string = '30d'): Promise<TimeSeriesPoint[]> {
  const res = await adminAxios.get<TimeSeriesPoint[]>('/admin/analytics/timeseries', {
    params: { period },
  });
  return res.data;
}

export async function fetchTenantsUsage(params: {
  page?: number;
  limit?: number;
  search?: string;
  sort?: string;
  order?: string;
  period?: string;
}): Promise<PaginatedResponse<TenantUsage>> {
  const res = await adminAxios.get<PaginatedResponse<TenantUsage>>('/admin/analytics/tenants', {
    params,
  });
  return res.data;
}

export async function fetchTenantAnalytics(
  tenantId: string,
  period: string = '30d'
): Promise<TenantAnalyticsDetail> {
  const res = await adminAxios.get<TenantAnalyticsDetail>(
    `/admin/analytics/tenant/${tenantId}`,
    { params: { period } }
  );
  return res.data;
}

export async function fetchTopTenants(
  sort: string = 'messages',
  limit: number = 10
): Promise<TenantUsage[]> {
  const res = await adminAxios.get<TenantUsage[]>('/admin/analytics/top-tenants', {
    params: { sort, limit },
  });
  return res.data;
}

export async function fetchModelLeaderboard(
  period: string = '30d'
): Promise<ModelUsage[]> {
  const res = await adminAxios.get<ModelUsage[]>('/admin/analytics/models', {
    params: { period },
  });
  return res.data;
}
