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

function useToken(): string {
  return useAuthStore((s) => s.token) ?? "";
}

export function useAccountList(page = 1, pageSize = 50) {
  const token = useToken();
  return useQuery({
    queryKey: ["accounts", page, pageSize],
    queryFn: () => fetchAccounts(token, page, pageSize),
    enabled: Boolean(token),
  });
}

export function useAccountSummary(domain: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["account", domain],
    queryFn: () => fetchAccountSummary(domain, token),
    enabled: Boolean(token) && Boolean(domain),
  });
}

export function useFatigueScore(domain: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["fatigue", domain],
    queryFn: () => fetchFatigueScore(domain, token),
    enabled: Boolean(token) && Boolean(domain),
  });
}

export function useIntentScore(domain: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["intent", domain],
    queryFn: () => fetchIntentScore(domain, token),
    enabled: Boolean(token) && Boolean(domain),
  });
}

export function useNBA(domain: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["nba", domain],
    queryFn: () => fetchNBA(domain, token),
    enabled: Boolean(token) && Boolean(domain),
  });
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
