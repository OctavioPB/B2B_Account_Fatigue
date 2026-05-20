// Typed API functions for account data — always imported from here, never raw fetch.

import {
  Account,
  AccountFatigueScore,
  AccountListResponse,
  AccountSummary,
  IntentScore,
  NextBestAction,
} from "@/lib/types";
import { api } from "./index";

export async function fetchAccounts(
  token: string,
  page = 1,
  pageSize = 50
): Promise<AccountListResponse> {
  return api.get<AccountListResponse>(
    `/accounts?page=${page}&page_size=${pageSize}`,
    token
  );
}

export async function fetchAccountSummary(
  domain: string,
  token: string
): Promise<AccountSummary> {
  return api.get<AccountSummary>(`/accounts/${encodeURIComponent(domain)}`, token);
}

export async function fetchFatigueScore(
  domain: string,
  token: string
): Promise<AccountFatigueScore> {
  return api.get<AccountFatigueScore>(
    `/accounts/${encodeURIComponent(domain)}/fatigue`,
    token
  );
}

export async function fetchIntentScore(
  domain: string,
  token: string
): Promise<IntentScore> {
  return api.get<IntentScore>(
    `/accounts/${encodeURIComponent(domain)}/intent`,
    token
  );
}

export async function fetchNBA(
  domain: string,
  token: string
): Promise<NextBestAction> {
  return api.get<NextBestAction>(
    `/accounts/${encodeURIComponent(domain)}/nba`,
    token
  );
}

export async function ingestSignal(
  domain: string,
  payload: {
    member_email: string;
    signal_type: string;
    channel: string;
    occurred_at: string;
    metadata?: Record<string, unknown>;
  },
  token: string
): Promise<{ accepted: boolean; signal_id: string; account_domain: string }> {
  return api.post(
    `/accounts/${encodeURIComponent(domain)}/signals`,
    payload,
    token
  );
}
