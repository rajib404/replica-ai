import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { clearAll, getOwnerId, getToken, setOwnerId, setToken } from "../store/auth";

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  accessToken: string | null;
  ownerId: string | null;
}

interface AuthContextValue extends AuthState {
  signIn: (tokens: { access_token: string; refresh_token: string }, ownerId: string) => Promise<void>;
  signOut: () => Promise<void>;
  updateAccessToken: (token: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    accessToken: null,
    ownerId: null,
  });

  useEffect(() => {
    Promise.all([getToken("access"), getOwnerId()]).then(([token, ownerId]) => {
      setState({ isAuthenticated: !!token, isLoading: false, accessToken: token, ownerId });
    });
  }, []);

  const signIn = async (
    tokens: { access_token: string; refresh_token: string },
    ownerId: string
  ) => {
    await setToken("access", tokens.access_token);
    await setToken("refresh", tokens.refresh_token);
    await setOwnerId(ownerId);
    setState({ isAuthenticated: true, isLoading: false, accessToken: tokens.access_token, ownerId });
  };

  const signOut = async () => {
    await clearAll();
    setState({ isAuthenticated: false, isLoading: false, accessToken: null, ownerId: null });
  };

  const updateAccessToken = (token: string) => {
    setState((prev) => ({ ...prev, accessToken: token }));
  };

  return (
    <AuthContext.Provider value={{ ...state, signIn, signOut, updateAccessToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
