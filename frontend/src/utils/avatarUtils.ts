export const getProxiedUrl = (url: any) => {
    if (!url) return undefined;
    if (typeof url === 'string' && url.startsWith('http') && !url.includes('127.0.0.1:8000')) {
        const API_BASE = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';
        return `${API_BASE}/api/v1/proxy/image?url=${encodeURIComponent(url)}`;
    }
    return url;
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
    const avatarUrl = data.avatar || 
                     data.profile_pic || 
                     data.photo || 
                     data.image || 
                     data.profile_image ||
                     data.linkedin_image ||
                     data.linkedin_metadata?.profile_image ||
                     getLinkedinAvatar(data.linkedin);
    
    if (!avatarUrl && data.email) {
        return `https://unavatar.io/${data.email}`;
    }
    
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
                    data.company_logo || 
                    data.logo || 
                    data.company_image ||
                    getCompanyLogoFallback();
    
    return logoUrl;
};
