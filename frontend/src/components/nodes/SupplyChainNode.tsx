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
  PanelRight
} from 'lucide-react';

export function SupplyChainNode({ data }: { data: any }) {
  const level = data.level !== undefined ? data.level : 5;
  const levelClass = styles[`level_${level}`] || '';

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
    <div className={`${styles.customNode} ${levelClass} ${data.isRoot ? styles.rootNode : ''}`}>
      {/* Decorative Lines for Theme handles */}
      <div className={styles.handleTopLine}></div>
      <Handle type="target" position={Position.Top} className={styles.handle} />
      
      {/* Top Badge Overlay */}
      <div className={styles.seniorityWrapper}>
        <ShieldCheck className="w-3.5 h-3.5" /> {seniorityLabel}
      </div>

      {/* Card Header (Technical Bar) */}
      <div className={styles.nodeHeader}>
        <div className={styles.levelBadge}>
          <Layers className="w-4 h-4" />
          <span>Tier {level}</span>
        </div>
        <div className={styles.headerBadges}>
          <GripHorizontal className="w-4 h-4 cursor-pointer hover:text-white transition-colors" />
          <PanelRight className="w-4 h-4 cursor-pointer hover:text-white transition-colors" />
        </div>
      </div>

      {/* Main Content Area */}
      <div className={styles.nodeBody}>
        <div className={styles.nodeNameWrapper}>
          <div className={styles.nodeAvatar}>
            {data.profile_pic ? (
              <img 
                src={`http://localhost:8000/api/v1/proxy/image?url=${encodeURIComponent(data.profile_pic)}`} 
                className="w-full h-full object-cover"
                onError={(e) => { (e.target as any).style.display = 'none'; }}
                alt=""
              />
            ) : (
              <User className="w-6 h-6" />
            )}
          </div>
          <div className="flex flex-col">
            <h3 className={styles.nodeName}>{data.name || 'Professional'}</h3>
            <div className={styles.roleWrapper}>
              <span className={styles.roleDept}>
                <Briefcase className="w-3.5 h-3.5" /> {data.role || 'Professional'}
              </span>
              <span className={styles.roleDot}></span>
              <span className={styles.roleCompany}>
                <Building2 className="w-3.5 h-3.5" /> {data.department || 'Business Unit'}
              </span>
            </div>
          </div>
        </div>

        {/* OSINT Enrichment Section */}
        <div className={styles.osintSection}>
          <span className={styles.osintLabel}>Metadados OSINT</span>
          <div className={styles.osintBox}>
            <div className={styles.osintLine}>
              <MapPin className={styles.osintIcon} />
              <span className={styles.osintText}>{data.location || 'Localização não identificada'}</span>
            </div>
            <div className={`${styles.osintLine} bg-[#0E0F12]/50 items-start`}>
              <GraduationCap className={styles.osintIcon} style={{ marginTop: '2px' }} />
              <p className={styles.osintParagraph}>
                {data.education || data.observations || 'Nenhuma informação adicional disponível via OSINT.'}
              </p>
            </div>
          </div>
        </div>

        {/* Contact/Intelligence Status */}
        <div className={styles.statusContainer}>
          <div className={styles.statusBox}>
            <div className={styles.statusIconWrapper}>
              <Mail className="w-3.5 h-3.5 text-[#A1A1AA]" />
            </div>
            <span className={styles.statusText}>
              {data.email ? data.email.toLowerCase() : 'gerando email...'}
            </span>
          </div>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} className={styles.handle} />
      <div className={styles.handleBottomLine}></div>
    </div>
  );
}

export const nodeTypes = {
  supplyChain: SupplyChainNode,
};
