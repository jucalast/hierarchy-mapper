import React from 'react';
import { Handle, Position } from 'reactflow';
import styles from '../NetworkGraph.module.css';

const LinkedInIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
  </svg>
);

const PinIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);

const SchoolIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
    <path d="M6 12v5c3 3 9 3 12 0v-5" />
  </svg>
);

const InfoIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

export function SupplyChainNode({ data }: { data: any }) {
  const level = data.level !== undefined ? data.level : 5;
  const levelClass = styles[`level_${level}`] || '';

  let seniorityLabel = "Operational";
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

  // Helper para formatar texto bruto
  const formatText = (text: string) => {
    if (!text || text === "N/A") return null;
    return text.toLowerCase().split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  return (
    <div className={`${styles.customNode} ${levelClass} ${data.isRoot ? styles.rootNode : ''}`}>
      <Handle type="target" position={Position.Top} className={styles.handle} />
      
      <div className={styles.nodeHeader}>
        <span className={styles.seniorityTag}>{seniorityLabel}</span>
        <div className={styles.headerBadges}>
          {data.connections && data.connections !== 'N/A' && (
            <span className={styles.connBadge}>{data.connections}</span>
          )}
          <span className={styles.levelBadge}>Tier {level}</span>
        </div>
      </div>

      <div className={styles.nodeBody}>
        <h3 className={styles.nodeName}>{data.name || 'Professional'}</h3>
        <p className={styles.nodeRole}>{data.role || 'Procurement Lead'}</p>
        
        {data.department && (
          <div className={styles.deptBadge}>
            {data.department}
          </div>
        )}

        {/* 🏢 INTELIGÊNCIA (LOCATION & SCHOOL) */}
        {(data.location || data.education) && (
          <div className={styles.deepDataBox}>
             {data.location && data.location !== 'N/A' && (
               <div className={styles.metaLine}>
                 <span className={styles.metaIcon}><PinIcon /></span>
                 {formatText(data.location)}
               </div>
             )}
             {data.education && data.education !== 'N/A' && (
               <div className={styles.metaLine}>
                 <span className={styles.metaIcon}><SchoolIcon /></span>
                 {formatText(data.education)}
               </div>
             )}
          </div>
        )}

        {/* 🏆 TAGS & SELOS */}
        {data.highlights && data.highlights !== 'N/A' && (
          <div className={styles.highlightsContainer}>
            {data.highlights.split(',').map((tag: string) => (
              <span key={tag} className={styles.highlightPill}>{tag.trim()}</span>
            ))}
          </div>
        )}
      </div>

      <div className={styles.nodeFooter}>
        <div className={styles.contactRow}>
          {data.email && <span className={styles.emailText}>{data.email.toLowerCase()}</span>}
        </div>
        
        <div className={styles.footerActions}>
          {data.linkedin && (
            <a 
              href={data.linkedin.startsWith('http') ? data.linkedin : `https://${data.linkedin}`} 
              target="_blank" 
              rel="noopener noreferrer" 
              className={`${styles.linkedinBtn} nodrag`}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <LinkedInIcon />
              <span>LinkedIn</span>
            </a>
          )}
          {data.observations && (
            <div 
              className={`${styles.infoIcon} nodrag`} 
              title={data.observations}
              onClick={(e) => {
                e.stopPropagation();
                alert(`ℹ️ Inteligência do Perfil:\n\n${data.observations}`);
              }}
            >
               <InfoIcon />
            </div>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
}

export const nodeTypes = {
  supplyChain: SupplyChainNode,
};
