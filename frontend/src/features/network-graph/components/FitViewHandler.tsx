"use client";

import React, { useEffect } from 'react';
import { Node } from 'reactflow';
import { useReactFlow } from 'reactflow';

interface FitViewHandlerProps {
    shouldFitView: boolean;
    nodes: Node[];
}

export const FitViewHandler: React.FC<FitViewHandlerProps> = ({ shouldFitView, nodes }) => {
    const { fitView } = useReactFlow();

    useEffect(() => {
        if (shouldFitView && nodes.length > 0) {
            setTimeout(() => {
                fitView({ padding: 0.2, duration: 800 });
            }, 100);
        }
    }, [shouldFitView, nodes, fitView]);

    return null;
};
