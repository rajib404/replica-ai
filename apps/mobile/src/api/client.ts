import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { clearAll, getToken, setToken } from "../store/auth";
import { ENDPOINTS } from "./endpoints";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_URL,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use(async (config) => {
  const token = await getToken("access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach((p) => (token ? p.resolve(token) : p.reject(error)));
  failedQueue = [];
}

apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({
          resolve: (token) => {
            original.headers.Authorization = `Bearer ${token}`;
            resolve(apiClient(original));
          },
          reject,
        });
      });
    }

    original._retry = true;
    isRefreshing = true;

    try {
      const refreshToken = await getToken("refresh");
      if (!refreshToken) throw new Error("No refresh token");

      // Response shape: { tokens: { access_token, refresh_token, token_type } }
      const { data } = await axios.post(`${API_URL}${ENDPOINTS.AUTH_REFRESH}`, {
        refresh_token: refreshToken,
      });

      const newAccess: string = data.tokens.access_token;
      const newRefresh: string = data.tokens.refresh_token;

      await setToken("access", newAccess);
      await setToken("refresh", newRefresh);
      original.headers.Authorization = `Bearer ${newAccess}`;
      processQueue(null, newAccess);
      return apiClient(original);
    } catch (refreshError) {
      processQueue(refreshError, null);
      await clearAll();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
