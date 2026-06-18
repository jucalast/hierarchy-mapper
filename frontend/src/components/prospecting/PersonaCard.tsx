import React, { memo, useMemo } from 'react';
import styles from '../network-graph/styles/Nodes.module.css';
import {
  MapPin,
  GraduationCap,
  Briefcase,
  Mail,
  Building2,
  Phone,
  ShieldCheck,
  Layers,
  X,
  Trash2,
  Brain,
  Quote,
  Info,
  Loader2
} from 'lucide-react';

import { getAvatarUrl, getCompanyLogoUrl, getProxiedUrl } from '../../utils/avatarUtils';
import { Dropdown } from '../ui/Dropdown';

function PersonaCardBase({ data, level, isNode = false }: { data: any, level?: number, isNode?: boolean }) {
  const dropdownItems = useMemo(() => [
    {
      label: 'Detalhes e Configurações',
      onClick: () => data.onEdit?.(data.id),
      icon: <Info size={14} />
    },
    {
      label: 'Excluir Perfil',
      onClick: () => data.onDelete?.(data.id),
      icon: <Trash2 size={14} />,
      danger: true
    }
  ], [data.onEdit, data.onDelete, data.id]);

  // Prioriza o nível vindo dos dados (backend) sobre o default do componente
  const effectiveLevel = data.seniority !== undefined ? Number(data.seniority) : (level ?? 5);
  
  let seniorityLabel = "Operational / Support";
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

  const avatarUrl = getAvatarUrl(data);
  const companyLogoUrl = getCompanyLogoUrl(data);

  return (
    <div 
        className={`${styles.customNode} ${!isNode ? styles.chatNode : ''} ${styles['level_' + effectiveLevel]} ${data.isRoot ? styles.rootNode : ''}`} 
        style={!isNode ? { position: 'relative', width: '300px', margin: '20px 0 10px 20px', zoom: 0.85 } : {}}
    >
      {isNode && <div className={styles.handleTopLine}></div>}
      
      {/* Top Badge Overlay */}
      <div className={`${styles.seniorityWrapper} ${styles['badge_' + effectiveLevel]}`}>
        <ShieldCheck size={14} /> {seniorityLabel}
      </div>

      {/* Card Header (Technical Bar) */}
      <div className={styles.nodeHeader}>
        <div className={styles.levelBadge}>
          <Layers size={14} />
          <span>Tier {effectiveLevel}</span>
          {data.isLoading && (
            <Loader2 
                size={16} 
                style={{ 
                    animation: 'spin 1s linear infinite', 
                    color: '#a855f7',
                    marginLeft: '8px'
                }} 
            />
          )}
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {data.matching_score > 0 && (
            <div className={styles.scoreBadge} title="IA Matching Score">
              {data.matching_score}%
            </div>
          )}

          {isNode && !data.isRoot && (
            <Dropdown 
              items={dropdownItems}
              iconType="vertical"
              iconSize={16}
              title="Mais opções"
            />
          )}
        </div>
      </div>

      <div className={styles.nodeBody}>
      <div className={styles.nodeNameWrapper}>
        {(data.linkedin || effectiveLevel === 0) && (          <div className={styles.nodeAvatarContainer}>
            <div className={styles.nodeAvatar}>
              {effectiveLevel === 0 ? (
                <img 
                  src={getProxiedUrl(data.confirmedLogo || data.company_logo || data.logo || data.avatar || data.image || data.logo_url || data.brand_logo || (data.domain ? "https://unavatar.io/" + data.domain : null))} 
                  alt="Company" 
                  className={styles.avatarImg} 
                  style={{ objectFit: "cover", background: "#fff" }} 
                  loading="lazy" 
                  decoding="async" 
                  onError={(e) => { 
                    const target = e.target as HTMLImageElement; 
                    const fallbackName = data.name || data.company || "K"; 
                    if (!target.src.includes("ui-avatars")) { 
                      target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(fallbackName)}&background=000&color=fff`; 
                    } 
                  }} 
                />
              ) : data.linkedin ? (
                <img 
                  src={getProxiedUrl(avatarUrl)} 
                  alt={data.name} 
                  className={styles.avatarImg} 
                  loading="lazy" 
                  decoding="async" 
                  onError={(e) => { 
                    const target = e.target as HTMLImageElement; 
                    target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(data.name)}&background=6366f1&color=fff&bold=true&rounded=true&size=128`; 
                  }} 
                />
              ) : null}
            </div>
            {effectiveLevel !== 0 && (data.linkedin || effectiveLevel === 6) && (
              <div className={styles.nodeAvatarCompanyBadge}>
                <img 
                  src={getProxiedUrl(companyLogoUrl)} 
                  alt="Company" 
                  className={styles.companyBadgeImg} 
                  loading="lazy" 
                  decoding="async" 
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(data.company || "C")}&background=000&color=fff`;
                  }}
                />
              </div>
            )}
          </div>

        )}
        
        <div className={styles.nodeTitles}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h3 className={styles.nodeName}>{data.name || 'Professional'}</h3>
            {data.linkedin && (
              <a
                href={data.linkedin.startsWith('http') ? data.linkedin : `https://${data.linkedin}`}
                target="_blank"
                rel="noopener noreferrer"
                className="nodrag"
                onPointerDown={(e) => e.stopPropagation()}
                style={{ display: 'inline-flex', alignItems: 'center', opacity: 0.55, transition: 'opacity 0.2s', flexShrink: 0 }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '0.9'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '0.55'; }}
              >
                <img src="/linkedin.png" alt="LinkedIn" style={{ width: 18, height: 18, objectFit: 'contain', borderRadius: 4 }} />
              </a>
            )}
          </div>
          <div className={styles.roleWrapper}>
            <span className={styles.roleDept}>
              <Briefcase size={14} /> {data.role || data.headline || 'Professional'}
            </span>
            <span className={styles.roleDot}></span>
            <span className={styles.roleCompany}>
              <Building2 size={14} /> {data.department || 'Business Unit'}
            </span>
          </div>
        </div>
      </div>

      {/* OSINT Enrichment Section */}
      <div className={styles.osintSection}>
        <div className={styles.osintBox}>
          {data.temperature && (
            <div className={`${styles.osintLine} ${styles.temperatureLine}`} style={{
              color: data.temperature === 'Quente' ? '#ef4444' : 
                     data.temperature === 'Morno' ? '#f59e0b' : 
                     data.temperature === 'Frio' ? '#3b82f6' : '#9ca3af',
              fontWeight: 'bold',
              backgroundColor: 'rgba(255,255,255,0.03)'
            }}>
              <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em', marginRight: '8px' }}>🔥 Temp. Lead: </span>
              <span className={styles.osintText} style={{ color: 'unset' }}>{data.temperature}</span>
            </div>
          )}
          <div className={styles.osintLine}>
            <MapPin className={styles.osintIcon} />
            <span className={styles.osintText}>{data.location || 'Localização não identificada'}</span>
          </div>
          {data.evidence && (
            <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
              <Brain className={styles.osintIcon} size={14} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'rgba(255, 255, 255, 0.4)', fontWeight: 600 }}>Veredito da IA</span>
                <p className={styles.osintParagraph}>
                  {data.evidence}
                </p>
              </div>
            </div>
          )}

          {(data.observations && data.observations !== 'N/A') && (
            <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
              <Quote className={styles.osintIcon} size={12} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'rgba(255, 255, 255, 0.4)', fontWeight: 600 }}>Bio Original</span>
                <p className={styles.osintParagraph}>
                  {data.observations}
                </p>
              </div>
            </div>
          )}

          {(data.education && data.education !== data.observations) && (
            <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
              <GraduationCap className={styles.osintIcon} />
              <p className={styles.osintParagraph}>
                {data.education}
              </p>
            </div>
          )}

          {!data.evidence && !data.education && !data.observations && (
             <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
              <p className={styles.osintParagraph} style={{ fontStyle: 'italic', opacity: 0.5 }}>
                Nenhuma informação adicional disponível.
              </p>
             </div>
          )}
          
          <div className={styles.emailLine}>
            <Mail size={14} className={styles.metaIcon} />
            <span className={styles.emailText}>{data.email || 'E-mail não cadastrado'}</span>
          </div>

          {/* TELEFONE / WHATSAPP / PABX */}
          {(data.phone || data.whatsapp || data.pabx || data.whatsapp_number) && (
            <div className={styles.emailLine} style={{ marginTop: '0px' }}>
              <Phone size={14} className={styles.metaIcon} />
              <span className={styles.emailText}>
                {data.whatsapp?.numero || data.phone || data.whatsapp_number || data.pabx}
              </span>
            </div>
          )}
        </div>
      </div>

      </div>

      {isNode && <div className={styles.handleBottomLine}></div>}
    </div>
  );
}

export const PersonaCard = memo(
  PersonaCardBase,
  (prev, next) => {
    if (prev.level !== next.level || prev.isNode !== next.isNode) return false;
    const a = prev.data || {};
    const b = next.data || {};
    return (
      a.id === b.id &&
      a.name === b.name &&
      a.role === b.role &&
      a.seniority === b.seniority &&
      a.department === b.department &&
      a.matching_score === b.matching_score &&
      a.evidence === b.evidence &&
      a.profile_pic === b.profile_pic &&
      a.headline === b.headline &&
      a.email === b.email &&
      a.phone === b.phone &&
      a.isLoading === b.isLoading
    );
  },
);
