import React from 'react';
import styles from './NetworkGraph.module.css';
import { User, MapPin, Building2, Briefcase } from 'lucide-react';
import { LinkedInIcon } from './icons/LinkedInIcon';

interface PersonaPreviewProps {
    data: any;
    position: { x: number; y: number };
    companyLogo?: string;
}

export function PersonaPreview({ data, position, companyLogo }: PersonaPreviewProps) {
    if (!data) return null;

    // Offset the preview slightly from the cursor to prevent flickering
    const style: React.CSSProperties = {
        left: position.x + 20,
        top: position.y - 40,
    };

    return (
        <div className={styles.personaPreview} style={style}>
            <div className={styles.previewHeader}>
                <div className={styles.previewAvatarGroup}>
                    <div className={styles.previewAvatar}>
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
                    {companyLogo && (
                        <div className={styles.previewCompanyLogo}>
                            <img 
                                src={companyLogo.startsWith('http') ? `http://localhost:8000/api/v1/proxy/image?url=${encodeURIComponent(companyLogo)}` : companyLogo}
                                className="w-full h-full object-contain"
                                alt=""
                            />
                        </div>
                    )}
                </div>
                <div>
                    <h4 className={styles.previewName}>{data.name || 'Professional'}</h4>
                    <span className={styles.previewRole}>{data.role || 'Senior Specialist'}</span>
                </div>
            </div>

            <p className={styles.previewBio}>
                {data.observations || data.education || 'Additional OSINT intelligence not available for this profile.'}
            </p>

            <div className={styles.previewMeta}>
                <div className={styles.previewMetaItem}>
                    <Briefcase className={styles.previewMetaIcon} size={12} />
                    <span>{data.department || 'Business Unit'}</span>
                </div>
                <div className={styles.previewMetaItem}>
                    <Building2 className={styles.previewMetaIcon} size={12} />
                    <span>{data.company || 'Enterprise'}</span>
                </div>
                <div className={styles.previewMetaItem}>
                    <MapPin className={styles.previewMetaIcon} size={12} />
                    <span>{data.location || 'Brasil'}</span>
                </div>
                <div className={styles.previewMetaItem}>
                    <LinkedInIcon className={styles.previewMetaIcon} size={12} />
                    <span>Linkedin Profile Verified</span>
                </div>
            </div>
        </div>
    );
}
