/** Transport profiles preserve the existing endpoint-specific error contracts. */
type JsonObject = Record<string, unknown>;
export type RequestOptions = { signal?: AbortSignal; httpError?: (status: number) => string };
type Profile = 'page' | 'platform' | 'semantic' | 'upload';

async function send<T>(profile: Profile, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = body === undefined ? {} : profile === 'upload'
    ? { method: 'POST', body: body as FormData }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  if (options.signal) init.signal = options.signal;
  const response = await fetch((profile === 'semantic' ? '/api/semantic/' : '/api/') + path, init);
  if (profile === 'page' && !response.ok) {
    throw new Error(options.httpError?.(response.status) ?? `请求失败 (${response.status})，请检查本地服务。`);
  }
  const result: unknown = await response.json();
  if (!response.ok) {
    if (profile === 'semantic') {
      throw new Error(result && typeof result === 'object' && 'error' in result ? String(result.error) : '请求失败，请检查本地服务');
    }
    // Platform/upload historically read .error directly, including the null response behavior.
    const error = (result as JsonObject).error;
    if (profile === 'upload') throw new Error(error as string | undefined);
    throw new Error(typeof error === 'string' ? error : '请求失败');
  }
  return result as T;
}

export const pageRequest = <T = JsonObject>(path: string, body?: unknown, options?: RequestOptions): Promise<T> => send<T>('page', path, body, options);
export const platformRequest = <T = JsonObject>(path: string, body?: unknown, options?: { signal?: AbortSignal }): Promise<T> => send<T>('platform', path, body, options);
export const semanticRequest = <T>(path: string, body?: unknown, options?: { signal?: AbortSignal }): Promise<T> => send<T>('semantic', path, body, options);
export const uploadRequest = <T = JsonObject>(path: string, form: FormData, options?: { signal?: AbortSignal }): Promise<T> => send<T>('upload', path, form, options);
