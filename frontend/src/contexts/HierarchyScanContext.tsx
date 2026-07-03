'use client';

import React, { createContext, useContext, ReactNode } from 'react';
import { useHierarchyScan, UseHierarchyScanReturn } from '@/hooks/useHierarchyScan';

const HierarchyScanContext = createContext<UseHierarchyScanReturn | null>(null);

export function HierarchyScanProvider({ children }: { children: ReactNode }) {
    const scan = useHierarchyScan();

    return (
        <HierarchyScanContext.Provider value={scan}>
            {children}
        </HierarchyScanContext.Provider>
    );
}

export function useGlobalHierarchyScan() {
    const context = useContext(HierarchyScanContext);
    if (!context) {
        throw new Error('useGlobalHierarchyScan must be used within a HierarchyScanProvider');
    }
    return context;
}
