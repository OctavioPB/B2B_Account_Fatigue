"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  tenantSlug: string | null;
  isAuthenticated: boolean;
  login: (token: string, tenantSlug: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      tenantSlug: null,
      isAuthenticated: false,

      login: (token, tenantSlug) => {
        // Store token in cookie so Next.js middleware can read it server-side
        document.cookie = `harmoni_token=${token}; path=/; max-age=3600; SameSite=Strict`;
        set({ token, tenantSlug, isAuthenticated: true });
      },

      logout: () => {
        document.cookie = "harmoni_token=; path=/; max-age=0";
        set({ token: null, tenantSlug: null, isAuthenticated: false });
      },
    }),
    {
      name: "harmoni-auth",
      partialize: (state) => ({
        token: state.token,
        tenantSlug: state.tenantSlug,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
