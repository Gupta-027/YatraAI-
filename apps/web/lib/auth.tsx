'use client';

import { useRouter } from 'next/navigation';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { ApiRequestError, api, getToken, setToken } from './api';
import type { User } from './types';

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  signInAsDemo: () => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch (error) {
      // An expired or invalid token should log the user out quietly rather than
      // leaving the app in a half-authenticated state.
      if (error instanceof ApiRequestError && error.isAuthError) setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onAuthChange = () => void refresh();
    window.addEventListener('yatraai:auth', onAuthChange);
    window.addEventListener('storage', onAuthChange);
    return () => {
      window.removeEventListener('yatraai:auth', onAuthChange);
      window.removeEventListener('storage', onAuthChange);
    };
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      async signIn(email, password) {
        const response = await api.login({ email, password });
        setToken(response.access_token);
        setUser(response.user);
      },
      async signUp(email, password, displayName) {
        const response = await api.register({
          email,
          password,
          display_name: displayName,
        });
        setToken(response.access_token);
        setUser(response.user);
      },
      async signInAsDemo() {
        const response = await api.demoLogin();
        setToken(response.access_token);
        setUser(response.user);
      },
      signOut() {
        setToken(null);
        setUser(null);
        router.push('/');
      },
      refresh,
    }),
    [user, loading, refresh, router]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

/** Redirects to sign-in when unauthenticated. Returns the user once known. */
export function useRequireAuth() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace('/login?next=' + encodeURIComponent(window.location.pathname));
  }, [user, loading, router]);
  return { user, loading };
}
