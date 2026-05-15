import React from 'react';
import { Background, BackgroundVariant, useStore } from 'reactflow';

/**
 * SmartBackground Component
 * Adjusts the grid gap based on zoom to prevent it from becoming too dense when zooming out.
 */
export const SmartBackground: React.FC = () => {
    // Get the current zoom from the ReactFlow store
    const transform = useStore((s) => s.transform);
    const zoom = transform[2];

    // Calculate a gap that stops shrinking after zoom 0.5
    // Visual gap = gap * zoom. If we want visual gap >= 20px, then gap = 20 / zoom.
    // We'll base it on 44px standard.
    const baseGap = 44;
    const minZoomForScale = 0.5;
    const effectiveGap = zoom < minZoomForScale ? (baseGap * minZoomForScale) / zoom : baseGap;

    return (
        <Background
            variant={BackgroundVariant.Lines}
            gap={effectiveGap}
            size={1}
            color="rgba(255, 255, 255, 0.05)"
        />
    );
};
