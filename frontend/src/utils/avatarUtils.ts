import { buildProxyImageUrl } from '@/services/config';

/**
 * Wrapper legado — delega ao helper centralizado em services/config.
 * Mantido para compatibilidade com componentes existentes.
 */
export const getProxiedUrl = (url: unknown): string | undefined => {
    if (typeof url !== 'string') return undefined;
    return buildProxyImageUrl(url);
};

export const getLinkedinAvatar = (linkedinUrl: string | null | undefined) => {
    if (!linkedinUrl) return null;
    let username = linkedinUrl;
    if (username.includes('linkedin.com/in/')) {
        const match = username.match(/linkedin\.com\/in\/([^\/\?#]+)/);
        if (match && match[1]) {
            username = match[1];
        }
    }
    username = username.split('/')[0].split('?')[0].trim();
    if (!username) return null;
    return `https://unavatar.io/linkedin/${username}`;
};

export const getAvatarUrl = (data: any) => {
    const avatarUrl = data.avatar_url ||
                     data.avatar || 
                     data.profile_pic || 
                     data.photo || 
                     data.image || 
                     data.profile_image ||
                     data.linkedin_image ||
                     data.linkedin_metadata?.profile_image ||
                     getLinkedinAvatar(data.linkedin);
    
    // Comentado para evitar buscar imagens genéricas que muitas vezes falham
    // if (!avatarUrl && data.email) {
    //     return `https://unavatar.io/${data.email}`;
    // }
    
    return avatarUrl;
};

export const getCompanyLogoUrl = (data: any) => {
    const getCompanyLogoFallback = () => {
        const domain = data.domain || data.company_domain;
        if (domain) return `https://unavatar.io/${domain}`;
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

    const logoUrl = data.confirmedLogo || 
                    data.logo_url ||
                    data.company_logo || 
                    data.logo || 
                    data.company_image ||
                    getCompanyLogoFallback();
    
    return logoUrl;
};
