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

export const getAvatarUrl = (data: any): string | null | undefined => {
    if (!data) return null;
    const avatarUrl = data.logo || 
                     data.avatar_url ||
                     data.avatar || 
                     data.profile_pic || 
                     data.photo || 
                     data.image || 
                     data.profile_image ||
                     data.linkedin_image ||
                     data.linkedin_metadata?.profile_image ||
                     getLinkedinAvatar(data.linkedin) ||
                     (data.originalEmployee ? getAvatarUrl(data.originalEmployee) : null);
    
    // Comentado para evitar buscar imagens genéricas que muitas vezes falham
    // if (!avatarUrl && data.email) {
    //     return `https://unavatar.io/${data.email}`;
    // }
    
    return avatarUrl;
};

export const getCompanyLogoUrl = (data: any) => {
    if (!data) return null;

    const getCompanyLogoFallback = () => {
        const domain = data.domain || data.company_domain || data.org_id?.domain || data.organization?.domain;
        if (domain) return `https://unavatar.io/${domain}`;
        
        const email = data.email || data.org_id?.email || data.organization?.email;
        if (email && email.includes('@')) {
            const parts = email.split('@');
            const domainFromEmail = parts[parts.length - 1];
            const excluded = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'icloud.com'];
            if (!excluded.includes(domainFromEmail.toLowerCase())) {
                return `https://unavatar.io/${domainFromEmail}`;
            }
        }
        return null;
    };

    // Tentar encontrar o logo em diversas variações de nomes de campos e níveis de aninhamento
    const logoUrl = data.confirmedLogo || 
                    data.logo_url ||
                    data.company_logo || 
                    data.logo || 
                    data.organization_logo ||
                    data.brand_logo ||
                    data.company_image ||
                    data.org_id?.logo ||
                    data.org_id?.logo_url ||
                    data.organization?.logo ||
                    data.organization?.logo_url ||
                    getCompanyLogoFallback();
    
    return logoUrl;
};
