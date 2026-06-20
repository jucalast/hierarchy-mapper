import { useEffect } from 'react';
import { useReactFlow, Node } from 'reactflow';

interface FitViewHandlerProps {
    shouldFitView: boolean;
    nodes: Node[];
    setShouldFitView: (val: boolean) => void;
}

export const FitViewHandler = ({ shouldFitView, nodes, setShouldFitView }: FitViewHandlerProps) => {
    const { fitView } = useReactFlow();
    useEffect(() => {
        if (shouldFitView && nodes.length > 0) {
            const timer = setTimeout(() => {
                fitView({ padding: 0.2, duration: 800 });
                setShouldFitView(false);
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [shouldFitView, nodes, fitView, setShouldFitView]);

    return null;
};
