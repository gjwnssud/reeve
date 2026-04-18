export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    public readonly url: string,
    message?: string,
  ) {
    super(message ?? `HTTP ${status} at ${url}`);
    this.name = 'ApiError';
  }
}
