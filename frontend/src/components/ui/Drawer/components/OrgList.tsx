import React from 'react';
import { OrgListItem } from '../../../prospecting/OrgListItem';
import { getLinkedinAvatar } from '@/utils/avatarUtils';

interface OrgListProps {
    filteredOrgs: any[];
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
    graphEmployees?: any[];
    onOrgClick: (org: any) => void;
    setExpandedOrgId: (id: number) => void;
    fetchOrgDetails: (id: number) => void;
    toggleExpand: (e: React.MouseEvent, id: number) => void;
    scanningOrgIds: number[];
}

import { useRouter } from 'next/navigation';

const isPartnerNode = (emp: any) =>
    emp.level === 6 ||
    String(emp.id).startsWith('partner_') ||
    emp.department === 'Quadro de Sócios (QSA)' ||
    emp.department === 'Quadro Societário';

export const OrgList: React.FC<OrgListProps> = ({
    filteredOrgs,
    selectedOrgId,
    selectedOrgLogo,
    graphEmployees = [],
    onOrgClick,
    setExpandedOrgId,
    fetchOrgDetails,
    toggleExpand,
    scanningOrgIds,
}) => {
    const router = useRouter();

    // Pré-calcula fotos da empresa selecionada a partir do graphEmployees
    // (inclui funcionários regulares + sócios, apenas quem tem profile_pic real)
    const selectedPics: string[] = (() => {
        if (!graphEmployees.length) return [];

        const allVisible = graphEmployees.filter(emp =>
            emp.id !== 'root_company' &&
            (!emp.role || !emp.role.toLowerCase().includes('humana')) &&
            emp.role !== 'Reprovado' &&
            emp.department !== 'Reprovado'
        );

        const pics = allVisible
            .map((emp: any) => {
                const saved = emp.profile_pic || emp.avatar;
                if (saved && saved.length > 10) return saved;
                // Fallback: unavatar.io via LinkedIn (mesma lógica do node card)
                return getLinkedinAvatar(emp.linkedin || emp.url) || null;
            })
            .filter((pic): pic is string => !!pic && pic.length > 10);

        return [...new Set(pics)];
    })();

    const selectedCount = graphEmployees.filter(emp =>
        emp.id !== 'root_company' &&
        (!emp.role || !emp.role.toLowerCase().includes('humana')) &&
        emp.role !== 'Reprovado' &&
        emp.department !== 'Reprovado'
    ).length;

    return (
        <>
            {filteredOrgs.map(org => {
                const orgId = Number(org.id);
                const isSelected = orgId === selectedOrgId;

                // Empresa selecionada: usa graphEmployees (inclui sócios do grafo atual)
                // Demais empresas: usa employee_pics do Pipedrive (pre-carregado pelo backend)
                const displayPics = isSelected && selectedPics.length > 0
                    ? selectedPics
                    : (org.employee_pics || []);

                const displayCount = isSelected && selectedCount > 0
                    ? selectedCount
                    : (org.employee_count || org.mapped_count || 0);

                const orgWithLogo = isSelected && !org.logo && selectedOrgLogo
                    ? { ...org, logo: selectedOrgLogo }
                    : org;

                return (
                    <OrgListItem
                        key={orgId}
                        org={orgWithLogo}
                        isSelected={isSelected}
                        onClick={(clickedOrg) => {
                            onOrgClick(clickedOrg);
                            const clickedOrgId = Number(clickedOrg.id || clickedOrg.pipedrive_id);
                            setExpandedOrgId(clickedOrgId);
                            void fetchOrgDetails(clickedOrgId);
                        }}
                        onMouseEnter={() => {
                            router.prefetch(`/org/${orgId}`);
                        }}
                        onToggleExpand={toggleExpand}
                        displayCount={displayCount}
                        displayPics={displayPics}
                        scanningOrgIds={scanningOrgIds}
                    />
                );
            })}
        </>
    );
};
