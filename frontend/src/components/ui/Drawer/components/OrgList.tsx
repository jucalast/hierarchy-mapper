import React from 'react';
import { OrgListItem } from '../../../prospecting/OrgListItem';

interface OrgListProps {
    filteredOrgs: any[];
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
    graphEmployees?: any[];
    onOrgClick: (org: any) => void;
    setExpandedOrgId: (id: number) => void;
    fetchOrgDetails: (id: number) => void;
    toggleExpand: (e: React.MouseEvent, id: number) => void;
    scanningOrgId: number | null;
}

import { useRouter } from 'next/navigation';

export const OrgList: React.FC<OrgListProps> = ({
    filteredOrgs,
    selectedOrgId,
    selectedOrgLogo,
    graphEmployees = [],
    onOrgClick,
    setExpandedOrgId,
    fetchOrgDetails,
    toggleExpand,
    scanningOrgId,
}) => {
    const router = useRouter();
    return (
        <>
            {filteredOrgs.map(org => {
                const orgId = Number(org.id);
                const isSelected = orgId === selectedOrgId || Number(org.local_id) === selectedOrgId;

                let displayPics = org.employee_pics || [];
                let displayCount = org.employee_count || 0;

                if (isSelected && graphEmployees.length > 0) {
                    const validEmps = graphEmployees.filter(emp =>
                        emp.id !== 'root_company' &&
                        emp.department !== 'Quadro Societário' &&
                        emp.department !== 'Quadro de Sócios (QSA)' &&
                        emp.level !== 6 &&
                        !String(emp.id).startsWith('partner_') &&
                        (!emp.role || !emp.role.toLowerCase().includes('humana'))
                    );

                    const graphPics = validEmps
                        .map(emp => emp.profile_pic || emp.avatar)
                        .filter(pic => pic && pic.length > 10);

                    displayPics = graphPics;
                    displayCount = validEmps.length;
                }

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
                        scanningOrgId={scanningOrgId}
                    />
                );
            })}
        </>
    );
};
