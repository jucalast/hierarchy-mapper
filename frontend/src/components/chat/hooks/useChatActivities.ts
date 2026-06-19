import { useState, useCallback } from 'react';
import { conversations } from '@/services/api';
import type { ActivityOut } from '@/services/api/conversations';

export const useChatActivities = (selectedOrgId?: number | null) => {
    const [activities, setActivities] = useState<ActivityOut[]>([]);
    const [isLoadingActivities, setIsLoadingActivities] = useState(false);

    const refreshActivities = useCallback(async () => {
        if (!selectedOrgId) return;
        setIsLoadingActivities(true);
        try {
            const acts = await conversations.listActivities(selectedOrgId);
            setActivities(acts);
        } catch { /* silent */ } finally {
            setIsLoadingActivities(false);
        }
    }, [selectedOrgId]);

    return {
        activities,
        setActivities,
        isLoadingActivities,
        setIsLoadingActivities,
        refreshActivities,
    };
};
