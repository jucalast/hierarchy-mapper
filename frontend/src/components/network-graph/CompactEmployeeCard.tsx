import React, { memo } from 'react';
import { ShieldCheck, Briefcase, User2 } from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../../utils/avatarUtils';

interface CompactEmployeeCardProps {
    data: any;
}

const CompactEmployeeCardBase: React.FC<CompactEmployeeCardProps> = ({ data }) => {
    const effectiveLevel = data.seniority !== undefined ? Number(data.seniority) : (data.level ?? 5);
    
    let seniorityLabel = "Professional";
    switch (effectiveLevel) {
        case 0: seniorityLabel = "Root Entity"; break;
        case 6: seniorityLabel = "Board / C-Level"; break;
        case 5: seniorityLabel = "Director / Regional Head"; break;
        case 4: seniorityLabel = "Manager / Group Leader"; break;
        case 3: seniorityLabel = "Coordinator / Project Owner"; break;
        case 2: seniorityLabel = "Specialist / Senior / Engineer"; break;
        case 1: seniorityLabel = "Operational / Support"; break;
        default: seniorityLabel = "Professional"; break;
    }

    const seniorityColor = React.useMemo(() => {
        switch (effectiveLevel) {
            case 6: return '#7A8BFF'; // Board
            case 5: return '#60A5FA'; // C-Level
            case 4: return '#2DD4BF'; // Director
            case 3: return '#4ADE80'; // Manager
            case 2: return '#FBBF24'; // Coordinator
            case 1: return '#A1A1AA'; // Specialist
            case 0: return '#F4F4F5'; // Root
            default: return 'rgba(255, 255, 255, 0.4)';
        }
    }, [effectiveLevel]);

    const avatarUrl = React.useMemo(() => getAvatarUrl(data), [data]);
    const proxiedAvatarUrl = React.useMemo(() => getProxiedUrl(avatarUrl), [avatarUrl]);

    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            backgroundColor: 'transparent', // Sem background como solicitado
            padding: '10px 14px',
            borderRadius: '12px',
            border: 'var(--sw-border-width) solid var(--sw-border)',
            transition: 'all 0.2s ease',
            cursor: 'default',
            width: '100%',
            maxWidth: '100%',
            marginBottom: '4px'
        }}>
            {/* Avatar Section */}
            <div style={{
                position: 'relative',
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                overflow: 'hidden',
                backgroundColor: '#dfe5e7',
                flexShrink: 0
            }}>
                {avatarUrl ? (
                    <img 
                        src={proxiedAvatarUrl} 
                        alt={data.name} 
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        loading="lazy"
                        decoding="async"
                        onError={(e) => { 
                            const target = e.target as HTMLImageElement; 
                            target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(data.name || 'P')}&background=dfe5e7&color=868686&bold=true&rounded=true&size=128`; 
                        }} 
                    />
                ) : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#868686' }}>
                        <User2 size={18} />
                    </div>
                )}
            </div>

            {/* Info Section */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                {/* Seniority Label - Agora acima do nome */}
                <div style={{
                    fontSize: '0.65rem',
                    fontWeight: 800,
                    color: seniorityColor,
                    // textTransform: 'uppercase', // Removido como solicitado
                    letterSpacing: '0.02em',
                    marginBottom: '2px',
                    opacity: 0.9
                }}>
                    {seniorityLabel}
                </div>

                <div style={{ 
                    fontSize: '0.85rem',
                    fontWeight: 700, 
                    color: 'rgba(255, 255, 255, 0.85)',
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    lineHeight: '1.2',
                    marginBottom: '1px'
                }}>
                    {data.name || 'Profissional'}
                </div>
                
                <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px',
                    fontSize: '0.7rem',
                    color: 'rgba(255, 255, 255, 0.4)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                }}>
                    {data.role || data.headline || 'Cargo não informado'}
                </div>
            </div>
        </div>
    );
};

export const CompactEmployeeCard = memo(
    CompactEmployeeCardBase,
    (prev, next) => {
        const a = prev.data || {};
        const b = next.data || {};
        return (
            a.id === b.id &&
            a.name === b.name &&
            a.role === b.role &&
            a.seniority === b.seniority &&
            a.level === b.level &&
            a.headline === b.headline &&
            a.profile_pic === b.profile_pic
        );
    },
);
