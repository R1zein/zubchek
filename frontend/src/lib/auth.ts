import { createClient } from "./mgxClient";

const client = createClient();

export interface UserSession {
  user_id: string;
  role: "doctor" | "patient";
  full_name: string;
  birth_date?: string | null;
}

const SESSION_KEY = "zubchek_session";

export function getSession(): UserSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

export function setSession(session: UserSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

/**
 * Get custom auth headers to send with API calls.
 * These headers identify the user to the backend.
 */
export function getAuthHeaders(): Record<string, string> {
  const session = getSession();
  if (!session) return {};
  return {
    "X-User-Id": session.user_id,
    "X-User-Role": session.role,
    "X-User-Name": session.full_name,
  };
}

/**
 * Make an authenticated API call with custom session headers.
 */
export async function authApiCall(params: {
  url: string;
  method: string;
  data?: any;
  options?: any;
}): Promise<any> {
  const session = getSession();
  const headers = session
    ? {
        "X-User-Id": session.user_id,
        "X-User-Role": session.role,
        "X-User-Name": session.full_name,
      }
    : {};

  return client.apiCall.invoke({
    ...params,
    data: {
      ...params.data,
      __headers: headers,
    },
    options: {
      ...params.options,
      headers,
    },
  });
}

export async function customLogin(params: {
  role: string;
  full_name?: string;
  login?: string;
  password: string;
}): Promise<UserSession> {
  let res: any;
  try {
    res = await client.apiCall.invoke({
      url: "/api/v1/custom-auth/login",
      method: "POST",
      data: params,
    });
  } catch (apiErr: any) {
    // Handle HTTP error responses (e.g., 428 for needs_password_setup)
    const detail =
      apiErr?.data?.detail ||
      apiErr?.response?.data?.detail ||
      apiErr?.message ||
      "";
    if (detail === "needs_password_setup") {
      const err = new Error("needs_password_setup");
      (err as any).code = "needs_password_setup";
      throw err;
    }
    throw new Error(detail || "Ошибка входа");
  }

  // Also check response body for non-success or needs_password_setup
  const detail = res?.data?.detail || "";
  if (detail === "needs_password_setup") {
    const err = new Error("needs_password_setup");
    (err as any).code = "needs_password_setup";
    throw err;
  }

  if (!res?.data?.success) {
    throw new Error(detail || "Ошибка входа");
  }

  const session: UserSession = {
    user_id: res.data.user_id,
    role: res.data.role,
    full_name: res.data.full_name,
    birth_date: res.data.birth_date || null,
  };
  setSession(session);
  return session;
}

export async function setPatientPassword(params: {
  login: string;
  new_password: string;
}): Promise<UserSession> {
  const res = await client.apiCall.invoke({
    url: "/api/v1/custom-auth/set-password",
    method: "POST",
    data: params,
  });

  if (!res?.data?.success) {
    throw new Error(res?.data?.detail || "Ошибка установки пароля");
  }

  const session: UserSession = {
    user_id: res.data.user_id,
    role: res.data.role,
    full_name: res.data.full_name,
    birth_date: res.data.birth_date || null,
  };
  setSession(session);
  return session;
}

export async function customRegister(params: {
  role: string;
  full_name: string;
  password: string;
  clinic_password?: string;
  patient_login?: string;
}): Promise<UserSession> {
  const res = await client.apiCall.invoke({
    url: "/api/v1/custom-auth/register",
    method: "POST",
    data: params,
  });

  if (!res?.data?.success) {
    throw new Error(res?.data?.detail || "Ошибка регистрации");
  }

  const session: UserSession = {
    user_id: res.data.user_id,
    role: res.data.role,
    full_name: res.data.full_name,
  };
  setSession(session);
  return session;
}

export function logout(): void {
  clearSession();
}

export { client };