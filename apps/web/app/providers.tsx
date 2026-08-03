'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiRequestError } from '@/lib/api';
import { AuthProvider } from '@/lib/auth';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Retrying an auth failure or a rate limit only makes things worse.
              if (error instanceof ApiRequestError) {
                if (error.isAuthError || error.isRateLimited || error.status === 404) return false;
              }
              return failureCount < 2;
            },
          },
          mutations: { retry: false },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
