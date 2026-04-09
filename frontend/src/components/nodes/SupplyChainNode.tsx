import React from 'react';
import { Handle, Position } from 'reactflow';
import styles from '../NetworkGraph.module.css';
import {
  MapPin,
  GraduationCap,
  User,
  Briefcase,
  ShieldCheck,
  Layers,
  Mail,
  Building2,
  GripHorizontal,
  PanelRight,
  ExternalLink
} from 'lucide-react';
import { LinkedInIcon } from '../icons/LinkedInIcon';


export function SupplyChainNode({ data }: { data: any }) {
  // Helper to proxy external images through our backend (bypasses CORS/Hotlinking blocks)
  const getProxiedUrl = (url: string) => {
    if (!url) return '';
    // Padronização Total: Todas as imagens externas agora passam pelo nosso Proxy do Backend
    // Isso evita qualquer bloqueio de CORS ou Hotlinking de qualquer fonte (LinkedIn, Google, Unavatar, etc)
    if (url.startsWith('http') && !url.includes('localhost:8000')) {
      return `http://localhost:8000/api/v1/proxy/image?url=${encodeURIComponent(url)}`;
    }
    return url;
  };

  // Extract LinkedIn username for avatar fallback

  const getLinkedinAvatar = () => {
    if (!data.linkedin) return null;
    let username = data.linkedin;
    if (username.includes('linkedin.com/in/')) {
      const match = username.match(/linkedin\.com\/in\/([^\/\?#]+)/);
      if (match && match[1]) {
        username = match[1];
      }
    }
    // Final cleanup: remove trailing slashes or queries
    username = username.split('/')[0].split('?')[0].trim();
    if (!username) return null;
    return `https://unavatar.io/linkedin/${username}`;
  };


  const avatarUrl = data.avatar || 
                   data.profile_pic || 
                   data.photo || 
                   data.image || 
                   data.profile_image ||
                   data.linkedin_image ||
                   data.linkedin_metadata?.profile_image ||
                   getLinkedinAvatar();


  // Extract Company domain for logo fallback
  const getCompanyLogo = () => {
    // If we have a direct domain field, use it
    const domain = data.domain || data.company_domain;
    if (domain) return `https://unavatar.io/${domain}`;

    // Fallback to extraction from email
    if (data.email && data.email.includes('@')) {
      const parts = data.email.split('@');
      const domainFromEmail = parts[parts.length - 1];
      const excluded = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'icloud.com'];
      if (!excluded.includes(domainFromEmail.toLowerCase())) {
        return `https://unavatar.io/${domainFromEmail}`;
      }
    }
    return null;
  };


  const companyLogoUrl = data.confirmedLogo || 
                        data.company_logo || 
                        data.logo || 
                        data.company_image ||
                        getCompanyLogo();


  const level = data.level !== undefined ? data.level : 5;



  let seniorityLabel = "Operational / Support";
  switch (level) {
    case 0: seniorityLabel = "Root Entity"; break;
    case 6: seniorityLabel = "Board / C-Level"; break;
    case 5: seniorityLabel = "Director / Regional Head"; break;
    case 4: seniorityLabel = "Manager / Group Leader"; break;
    case 3: seniorityLabel = "Coordinator / Project Owner"; break;
    case 2: seniorityLabel = "Specialist / Senior / Engineer"; break;
    case 1: seniorityLabel = "Operational / Support"; break;
    default: seniorityLabel = "Professional"; break;
  }

  return (
    <div className={`${styles.customNode} ${styles['level_' + level]} ${data.isRoot ? styles.rootNode : ''}`}>
      {/* Decorative Lines for Theme handles */}
      <div className={styles.handleTopLine}></div>
      <Handle type="target" position={Position.Top} className={styles.handle} />

      {/* Top Badge Overlay */}
      <div className={`${styles.seniorityWrapper} ${styles['badge_' + level]}`}>
        <ShieldCheck size={14} /> {seniorityLabel}
      </div>

      {/* Card Header (Technical Bar) */}
      <div className={styles.nodeHeader}>
        <div className={styles.levelBadge}>
          <Layers size={14} />
          <span>Tier {level}</span>
        </div>
      </div>



      {/* Main Content Area */}
      <div className={styles.nodeBody}>
        <div className={styles.nodeNameWrapper}>
          {(data.linkedin || level === 0) && (
            <div className={styles.nodeAvatar}>
              {data.linkedin ? (
                <>
                  <img 
                    src={getProxiedUrl(avatarUrl)} 
                    alt={data.name} 
                    className={styles.avatarImg}
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(data.name)}&background=6366f1&color=fff&bold=true&rounded=true&size=128`;
                    }}
                  />
                  
                  {/* Badge de Empresa (Overlay) para Pessoas */}
                  <div className={styles.nodeAvatarCompanyBadge}>
                    <img 
                      src={getProxiedUrl(data.company_logo || `https://unavatar.io/${data.domain || data.company || 'knorr-bremse.com'}`)} 
                      alt="Company" 
                      className={styles.companyBadgeImg}
                    />
                  </div>
                </>
              ) : (
                /* Logo da Empresa para o Nó Principal (Tier 0) */
                <img 
                  src={getProxiedUrl(data.company_logo || data.logo || data.image || data.logo_url || data.brand_logo || (data.domain ? `https://unavatar.io/${data.domain}` : ''))} 
                  alt="Company" 
                  className={styles.avatarImg}
                  style={{ objectFit: 'contain' }}
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    const fallbackName = data.name || data.company || 'K';
                    target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(fallbackName)}&background=000&color=fff`;
                  }}
                />
              )}
            </div>
          )}


          <div className={styles.nodeTitles}>
            <h3 className={styles.nodeName}>{data.name || 'Professional'}</h3>
            <div className={styles.roleWrapper}>
              <span className={styles.roleDept}>
                <Briefcase size={14} /> {data.role || 'Professional'}
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
            <div className={styles.osintLine}>
              <MapPin className={styles.osintIcon} />
              <span className={styles.osintText}>{data.location || 'Localização não identificada'}</span>
            </div>
            <div className={`${styles.osintLine} ${styles.osintLineMetadata}`}>
              <GraduationCap className={styles.osintIcon} />
              <p className={styles.osintParagraph}>
                {data.education || data.observations || 'Nenhuma informação adicional disponível via OSINT.'}
              </p>
            </div>
            <div className={styles.emailLine}>
              <Mail size={14} className={styles.metaIcon} />
              <span className={styles.emailText}>{data.email || 'gerando email...'}</span>
            </div>
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

      <Handle type="source" position={Position.Bottom} className={styles.handle} />
      <div className={styles.handleBottomLine}></div>
    </div>
  );
}

export const nodeTypes = {
  supplyChain: SupplyChainNode,
};
