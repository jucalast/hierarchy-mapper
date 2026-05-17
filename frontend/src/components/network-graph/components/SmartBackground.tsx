import React from 'react';
import { Background, BackgroundVariant, useStore } from 'reactflow';

export const SmartBackground = () => {
    const transform = useStore((s) => s.transform);
    const zoom = transform[2];
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
