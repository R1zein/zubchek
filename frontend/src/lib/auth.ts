import { createClient } from "./mgxClient";

const client = createClient();

export interface UserSession {
  user_id: string;
  access_token: string;
  role: "doctor" | "patient";
  full_name: string;
  birth_date?: string | null;
}

const SESSION_KEY = "zubchek_session";

export function getSession(): UserSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as UserSession;
    if (!session.access_token) { localStorage.removeItem(SESSION_KEY); return null; }
    return session;
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
 * Get the signed session header for API calls.
 */
export function getAuthHeaders(): Record<string, string> {
  const session = getSession();
  if (!session) return {};
  return {
    Authorization: `Bearer ${session.access_token}`,
  };
}

/**
 * Make an authenticated API call with the signed session.
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
        Authorization: `Bearer ${session.access_token}`,
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

/**
 * Result of an auth step: either the account still needs an emailed code
 * (needsVerification), or a session was established.
 */
export interface AuthResult {
  needsVerification: boolean;
  email?: string;
  session?: UserSession;
}

/** POST to a custom-auth endpoint, returning the response body or throwing the
 *  server's error detail as an Error. */
async function postAuth(url: string, data: Record<string, unknown>): Promise<any> {
  try {
    const res = await client.apiCall.invoke({ url, method: "POST", data });
    const body = res?.data ?? res;
    if (body?.detail && body?.success !== true) {
      throw new Error(body.detail);
    }
    return body;
  } catch (apiErr: any) {
    if (apiErr instanceof Error && apiErr.message && !(apiErr as any).data && !(apiErr as any).response) {
      throw apiErr;
    }
    const detail =
      apiErr?.data?.detail ||
      apiErr?.response?.data?.detail ||
      apiErr?.message ||
      "Ошибка";
    throw new Error(detail);
  }
}

/** Turn a backend AuthResponse body into an AuthResult, storing the session. */
function toAuthResult(body: any): AuthResult {
  if (body?.needs_verification) {
    return { needsVerification: true, email: body.email };
  }
  const session: UserSession = {
    user_id: body.user_id,
    access_token: body.access_token,
    role: body.role,
    full_name: body.full_name,
    birth_date: body.birth_date || null,
  };
  setSession(session);
  return { needsVerification: false, session };
}

// ---- Doctor: register + login + email verification (#3) ----

export async function registerDoctor(params: {
  full_name: string;
  email: string;
  password: string;
  clinic_password: string;
}): Promise<AuthResult> {
  const body = await postAuth("/api/v1/custom-auth/register", { role: "doctor", ...params });
  return toAuthResult(body);
}

export async function loginDoctor(params: {
  email: string;
  password: string;
}): Promise<AuthResult> {
  const body = await postAuth("/api/v1/custom-auth/login", { role: "doctor", ...params });
  return toAuthResult(body);
}

export async function verifyDoctorEmail(params: {
  email: string;
  code: string;
}): Promise<UserSession> {
  const body = await postAuth("/api/v1/custom-auth/verify-email", params);
  const result = toAuthResult(body);
  if (!result.session) throw new Error("Ошибка подтверждения");
  return result.session;
}

// ---- Patient: login via emailed code (#4) ----

export async function requestPatientCode(email: string): Promise<void> {
  await postAuth("/api/v1/custom-auth/patient/request-code", { email });
}

export async function verifyPatientCode(params: {
  email: string;
  code: string;
}): Promise<UserSession> {
  const body = await postAuth("/api/v1/custom-auth/patient/verify-code", params);
  const result = toAuthResult(body);
  if (!result.session) throw new Error("Ошибка входа");
  return result.session;
}

export function logout(): void {
  clearSession();
}

export { client };