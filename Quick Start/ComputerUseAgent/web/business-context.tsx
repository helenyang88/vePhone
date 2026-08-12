import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, setBusinessIdResolver } from "./api/client";
import type { BusinessSpace, BusinessSpaceListResponse } from "./api/types";

const STORAGE_KEY = "mua.currentBusinessId";
const DEFAULT_BUSINESS: BusinessSpace = {
  id: "biz_default",
  name: "默认业务",
  description: null,
  is_default: true,
  task_concurrency_limit: 4,
  archived_at: null,
  created_by: "system",
};

type BusinessContextValue = {
  businesses: BusinessSpace[];
  currentBusiness: BusinessSpace;
  setCurrentBusinessId: (businessId: string) => void;
  createBusiness: (payload: {
    name: string;
    description?: string | null;
    task_concurrency_limit: number;
  }) => Promise<BusinessSpace>;
  updateBusiness: (
    businessId: string,
    payload: {
      name?: string;
      description?: string | null;
      task_concurrency_limit?: number;
    },
  ) => Promise<void>;
  archiveBusiness: (businessId: string) => Promise<void>;
  isLoading: boolean;
};

const BusinessContext = createContext<BusinessContextValue | null>(null);

export function BusinessProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState(
    () => localStorage.getItem(STORAGE_KEY) || DEFAULT_BUSINESS.id,
  );

  const spaces = useQuery({
    queryKey: ["business-spaces"],
    queryFn: () => api.get<BusinessSpaceListResponse>("/business-spaces"),
    retry: false,
  });

  const businesses = spaces.data?.items?.length ? spaces.data.items : [DEFAULT_BUSINESS];
  const currentBusiness = (
    businesses.find((item) => item.id === selectedId)
    ?? businesses.find((item) => item.is_default)
    ?? DEFAULT_BUSINESS
  );

  useEffect(() => {
    if (currentBusiness.id !== selectedId) {
      setSelectedId(currentBusiness.id);
    }
    if (currentBusiness.id === DEFAULT_BUSINESS.id) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, currentBusiness.id);
    }
  }, [currentBusiness.id, selectedId]);

  useEffect(() => {
    setBusinessIdResolver(() => currentBusiness.id);
    return () => setBusinessIdResolver(null);
  }, [currentBusiness.id]);

  function setCurrentBusinessId(businessId: string) {
    setSelectedId(businessId);
    if (businessId === DEFAULT_BUSINESS.id) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, businessId);
    }
    void queryClient.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== "business-spaces",
    });
  }

  const createMutation = useMutation({
    mutationFn: (payload: {
      name: string;
      description?: string | null;
      task_concurrency_limit: number;
    }) =>
      api.post<BusinessSpace>("/business-spaces", payload),
    onSuccess: (created) => {
      queryClient.setQueryData<BusinessSpaceListResponse>(
        ["business-spaces"],
        (previous) => ({ items: [...(previous?.items ?? businesses), created] }),
      );
      setCurrentBusinessId(created.id);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      businessId,
      payload,
    }: {
      businessId: string;
      payload: {
        name?: string;
        description?: string | null;
        task_concurrency_limit?: number;
      };
    }) => api.patch<BusinessSpace>(`/business-spaces/${businessId}`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["business-spaces"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (businessId: string) =>
      api.post<BusinessSpace>(`/business-spaces/${businessId}/archive`),
    onSuccess: (archived) => {
      void queryClient.invalidateQueries({ queryKey: ["business-spaces"] });
      if (archived.id === currentBusiness.id) {
        setCurrentBusinessId(DEFAULT_BUSINESS.id);
      }
    },
  });

  const value = useMemo<BusinessContextValue>(
    () => ({
      businesses,
      currentBusiness,
      setCurrentBusinessId,
      createBusiness: (payload) => createMutation.mutateAsync(payload),
      updateBusiness: async (businessId, payload) => {
        await updateMutation.mutateAsync({ businessId, payload });
      },
      archiveBusiness: async (businessId) => {
        await archiveMutation.mutateAsync(businessId);
      },
      isLoading: spaces.isLoading,
    }),
    [
      archiveMutation,
      businesses,
      createMutation,
      currentBusiness,
      spaces.isLoading,
      updateMutation,
    ],
  );

  return <BusinessContext.Provider value={value}>{children}</BusinessContext.Provider>;
}

export function useBusinessContext(): BusinessContextValue | null {
  return useContext(BusinessContext);
}

export function defaultBusiness(): BusinessSpace {
  return DEFAULT_BUSINESS;
}
