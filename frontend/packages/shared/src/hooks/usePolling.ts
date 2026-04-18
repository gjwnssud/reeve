import { useQuery, type UseQueryResult } from '@tanstack/react-query';

export type UsePollingOptions<T> = {
  queryKey: readonly unknown[];
  fetcher: () => Promise<T>;
  intervalMs: number;
  enabled?: boolean;
};

export function usePolling<T>(opts: UsePollingOptions<T>): UseQueryResult<T> {
  return useQuery({
    queryKey: opts.queryKey,
    queryFn: opts.fetcher,
    enabled: opts.enabled ?? true,
    refetchInterval: opts.intervalMs,
    refetchIntervalInBackground: false,
  });
}
