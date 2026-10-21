export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {cache: "no-store", ...options,
    headers:{"Content-Type":"application/json", ...options?.headers}});
  if (!response.ok) {
    const body = await response.json().catch(()=>null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `서버 요청 실패 (${response.status}). 백엔드 실행 상태를 확인하세요.`);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export function post<T>(path: string, data?: unknown) {return api<T>(path,{method:"POST",body:data == null ? undefined : JSON.stringify(data)});}
