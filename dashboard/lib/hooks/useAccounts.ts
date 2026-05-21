"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchAccounts,
  fetchAccountSummary,
  fetchFatigueScore,
  fetchIntentScore,
  fetchNBA,
  ingestSignal,
} from "@/lib/api/accounts";
import { useAuthStore } from "@/lib/store/auth";
import { DEMO_ACCOUNT_LIST, DEMO_BY_DOMAIN } from "@/lib/demo/data";

function useToken(): string {
  return useAuthStore((s) => s.token) ?? "";
}

function useIsDemo(): boolean {
  return useAuthStore((s) => s.isDemo);
}

const DEMO_RESOLVED = { isLoading: false, isError: false, error: null } as const;

export function useAccountList(page = 1, pageSize = 50) {
  const token = useToken();
  const isDemo = useIsDemo();
  const liveResult = useQuery({
    queryKey: ["accounts", page, pageSize],
    queryFn: () => fetchAccounts(token, page, pageSize),
    enabled: Boolean(token) && !isDemo,
  });
  if (isDemo) return { ...DEMO_RESOLVED, data: DEMO_ACCOUNT_LIST };
  return liveResult;
}

export function useAccountSummary(domain: string) {
  const token = useToken();
  const isDemo = useIsDemo();
  const liveResult = useQuery({
    queryKey: ["account", domain],
    queryFn: () => fetchAccountSummary(domain, token),
    enabled: Boolean(token) && Boolean(domain) && !isDemo,
  });
  if (isDemo) {
    const entry = DEMO_BY_DOMAIN[domain] ?? Object.values(DEMO_BY_DOMAIN)[0];
    return { ...DEMO_RESOLVED, data: entry.summary };
  }
  return liveResult;
}

export function useFatigueScore(domain: string) {
  const token = useToken();
  const isDemo = useIsDemo();
  const liveResult = useQuery({
    queryKey: ["fatigue", domain],
    queryFn: () => fetchFatigueScore(domain, token),
    enabled: Boolean(token) && Boolean(domain) && !isDemo,
  });
  if (isDemo) {
    const entry = DEMO_BY_DOMAIN[domain] ?? Object.values(DEMO_BY_DOMAIN)[0];
    return { ...DEMO_RESOLVED, data: entry.summary.fatigue };
  }
  return liveResult;
}

export function useIntentScore(domain: string) {
  const token = useToken();
  const isDemo = useIsDemo();
  const liveResult = useQuery({
    queryKey: ["intent", domain],
    queryFn: () => fetchIntentScore(domain, token),
    enabled: Boolean(token) && Boolean(domain) && !isDemo,
  });
  if (isDemo) {
    const entry = DEMO_BY_DOMAIN[domain] ?? Object.values(DEMO_BY_DOMAIN)[0];
    return { ...DEMO_RESOLVED, data: entry.summary.intent };
  }
  return liveResult;
}

export function useNBA(domain: string) {
  const token = useToken();
  const isDemo = useIsDemo();
  const liveResult = useQuery({
    queryKey: ["nba", domain],
    queryFn: () => fetchNBA(domain, token),
    enabled: Boolean(token) && Boolean(domain) && !isDemo,
  });
  if (isDemo) {
    const entry = DEMO_BY_DOMAIN[domain] ?? Object.values(DEMO_BY_DOMAIN)[0];
    return { ...DEMO_RESOLVED, data: entry.summary.current_nba };
  }
  return liveResult;
}

export function useIngestSignal(domain: string) {
  const token = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof ingestSignal>[1]) =>
      ingestSignal(domain, payload, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["account", domain] });
    },
  });
}

export function useDemoAccountDetails(domain: string) {
  const isDemo = useIsDemo();
  if (!isDemo) return null;
  return DEMO_BY_DOMAIN[domain] ?? Object.values(DEMO_BY_DOMAIN)[0];
}
