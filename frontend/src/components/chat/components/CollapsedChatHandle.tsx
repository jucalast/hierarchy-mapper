import React, { useState } from 'react';
import { ChevronLeft } from 'lucide-react';

interface CollapsedChatHandleProps {
    onClick: () => void;
    theme?: string;
}

export const CollapsedChatHandle: React.FC<CollapsedChatHandleProps> = ({ onClick, theme = 'dark' }) => {
    const [isHovered, setIsHovered] = useState(false);
    
    const isLight = theme === 'light';

    // Dark Mode Styling
    const darkBg = 'var(--sw-sidebar)';
    const darkArrow = 'var(--sw-text-muted)';

    // Light Mode Styling
    const lightBg = 'var(--sw-primary)';
    const lightArrow = '#ffffff';

    const currentBg = isLight ? lightBg : darkBg;
    const currentArrowColor = isLight ? lightArrow : darkArrow;

    return (
        <div 
            style={{
                position: 'fixed',
                right: 0,
                top: '50%',
                transform: 'translateY(-50%)',
                backgroundColor: currentBg,
                borderTop: 'none',
                borderBottom: 'none',
                borderLeft: 'none',
                borderRight: 'none',
                borderRadius: '8px 0 0 8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end', // Mover a seta mais pra direita
                padding: '0 2px 0 0',
                width: isHovered ? '30px' : '24px',
                height: '80px',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                boxShadow: '-2px 0 8px rgba(0,0,0,0.2)',
                zIndex: 9999,
            }}
            onClick={onClick}
            title="Abrir Assistente de Vendas"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                color: currentArrowColor,
            }}>
                <ChevronLeft size={20} strokeWidth={2.5} />
            </div>
        </div>
    );
};
