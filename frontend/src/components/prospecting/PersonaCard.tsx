import React, { memo, useMemo } from 'react';
import styles from '../network-graph/NetworkGraph.module.css';
import {
  MapPin,
  GraduationCap,
  Briefcase,
  Mail,
  Building2,
  Phone,
  ShieldCheck,
  Layers
} from 'lucide-react';

import { getAvatarUrl, getCompanyLogoUrl, getProxiedUrl } from '../../utils/avatarUtils';

function PersonaCardBase({ data, level, isNode = false }: { data: any, level?: number, isNode?: boolean }) {
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
        </div>
        {data.matching_score > 0 && (
          <div className={styles.scoreBadge} title="IA Matching Score">
            {data.matching_score}%
          </div>
        )}
      </div>

      <div className={styles.nodeBody}>
      <div className={styles.nodeNameWrapper}>
        {(data.linkedin || effectiveLevel === 0) && (
          <div className={styles.nodeAvatar}>
            {effectiveLevel === 0 ? (
              <img 
                src={getProxiedUrl(data.confirmedLogo || data.company_logo || data.logo || data.avatar || data.image || data.logo_url || data.brand_logo || (data.domain ? "https://unavatar.io/" + data.domain : null))} 
                alt="Company" 
                className={styles.avatarImg} 
                style={{ objectFit: "contain", background: "#fff" }} 
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
              <>
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
                {effectiveLevel !== 6 && effectiveLevel !== 0 && (
                  <div className={styles.nodeAvatarCompanyBadge}>
                    <img 
                      src={getProxiedUrl(data.company_logo || `https://unavatar.io/${data.domain || data.company || "knorr-bremse.com"}`)} 
                      alt="Company" 
                      className={styles.companyBadgeImg} 
                      loading="lazy" 
                      decoding="async" 
                    />
                  </div>
                )}
              </>
            ) : null}
          </div>
        )}
        
        <div className={styles.nodeTitles}>
          <h3 className={styles.nodeName}>{data.name || 'Professional'}</h3>
          <div className={styles.roleWrapper}>
            <span className={styles.roleDept}>
              <Briefcase size={14} /> {data.headline || data.role || 'Professional'}
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
          <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
            <GraduationCap className={styles.osintIcon} />
            <p className={styles.osintParagraph}>
              {data.evidence || data.education || data.observations || 'Nenhuma informação adicional disponível via OSINT.'}
            </p>
          </div>
          
          <div className={styles.emailLine}>
            <Mail size={14} className={styles.metaIcon} />
            <span className={styles.emailText}>{data.email || 'gerando email...'}</span>
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

      {/* Action Footer */}
      {data.linkedin && (
        <div className={styles.nodeActionFooter}>
          <a
            href={data.linkedin.startsWith('http') ? data.linkedin : `https://${data.linkedin}`}
            target="_blank"
            rel="noopener noreferrer"
            className={`${styles.linkedinBtn} nodrag`}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <img src="/linkedin.png" alt="LinkedIn" className={styles.linkedinIconImg} />
            <span>Ver Perfil no LinkedIn</span>
          </a>
        </div>
      )}
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
      a.phone === b.phone
    );
  },
);
