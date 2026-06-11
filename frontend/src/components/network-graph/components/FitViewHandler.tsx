import { useEffect } from 'react';
import { useReactFlow, Node } from 'reactflow';

interface FitViewHandlerProps {
    shouldFitView: boolean;
    nodes: Node[];
}

export const FitViewHandler = ({ shouldFitView, nodes }: FitViewHandlerProps) => {
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
