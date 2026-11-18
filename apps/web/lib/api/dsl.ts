"use client";

/** DSL catalogue / JSON Schema hooks for the visual builder (Phase 5). */

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { DslCatalogue } from "./generated";
import { FALLBACK_CATALOGUE } from "../dsl-catalogue-fallback";

export const dslKeys = {
  catalogue: ["strategies", "dsl", "catalogue"] as const,
  schema: ["strategies", "dsl", "schema"] as const,
};

/** Merges the server catalogue over the local fallback so new enums appear without a deploy
 *  and missing fields never break the form. */
export function mergeCatalogue(remote: Partial<DslCatalogue> | null | undefined): DslCatalogue {
  if (!remote) return FALLBACK_CATALOGUE;
  const out: DslCatalogue = { ...FALLBACK_CATALOGUE };
  for (const key of Object.keys(FALLBACK_CATALOGUE) as (keyof DslCatalogue)[]) {
    const v = remote[key];
    if (Array.isArray(v) && v.length > 0) (out as unknown as Record<string, unknown>)[key] = v;
  }
  return out;
}

export function useDslCatalogue() {
  const q = useQuery({
    queryKey: dslKeys.catalogue,
    queryFn: () => api<Partial<DslCatalogue>>("/strategies/dsl/catalogue"),
    staleTime: 10 * 60_000,
    retry: 1,
  });
  return { catalogue: mergeCatalogue(q.data), fromServer: q.isSuccess, isPending: q.isPending, isError: q.isError };
}

export function useDslSchema() {
  return useQuery({
    queryKey: dslKeys.schema,
    queryFn: () => api<Record<string, unknown>>("/strategies/dsl/schema"),
    staleTime: 10 * 60_000,
    retry: 1,
  });
}
