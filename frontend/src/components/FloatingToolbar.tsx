import React from 'react';
import type { ProspectSession, ProspectLead } from '@/hooks/useProspecting';
import { ProspectingToolbar } from './FloatingToolbar/ProspectingToolbar';
import { NormalToolbar } from './FloatingToolbar/NormalToolbar';

export interface FloatingToolbarProps {
    error: string | null;
    handleSearch: (e: React.FormEvent) => void;
    cnpj: string;
    setCnpj: (val: string) => void;
    confirmedBrand: string;
    setConfirmedBrand: (val: string) => void;
    confirmedLogo: string;
    setConfirmedLogo: (val: string) => void;
    confirmedFollowers: string;
    setConfirmedFollowers: (val: string) => void;
    domainTarget: string;
    setDomainTarget: (val: string) => void;
    productFocus: string;
    setProductFocus: (val: string) => void;
    areaFocus: 'compras' | 'logistica';
    setAreaFocus: (val: 'compras' | 'logistica') => void;
    handleAutoEnrich: () => void;
    enrichingIds: Set<number>;
    discovering: boolean;
    loading: boolean;
    step: string;
    brandOptions: any[];
    onBrandSelect: (brandObj: any) => void;
    hasMapping?: boolean;
    stopHierarchyScan?: () => void;
    cancelDiscovery?: () => void;
    activeJobId?: string | null;
    onApproveCandidate?: (id: string) => void;
    onRejectCandidate?: (id: string) => void;

    // ── Modo Prospecção (só ativo quando activeView === 'prospecting') ──
    isProspectingMode?: boolean;
    prospectCoords?: { lat: number; lng: number } | null;
    prospectRadiusKm?: number;
    onProspectRadiusChange?: (km: number) => void;
    onProspectGeolocate?: () => void;
    prospectGeoLoading?: boolean;
    onProspectSearch?: () => void;
    onProspectStop?: () => void;
    prospectSearching?: boolean;
    prospectSession?: ProspectSession | null;
    prospectLeadsCount?: number;
    prospectTierACount?: number;
    prospectError?: string | null;
    prospectCityName?: string | null;
    onProspectCepLookup?: (cep: string) => Promise<void>;
    prospectSelectedLead?: ProspectLead | null;
    prospectPendingLeads?: ProspectLead[];
    onProspectSelectLead?: (lead: ProspectLead) => void;
    onProspectApproveLead?: (id: string) => Promise<void>;
    onProspectRejectLead?: (id: string) => Promise<void>;
    onProspectCloseLead?: () => void;
    prospectCep?: string;
    onProspectCepChange?: (cep: string) => void;
    prospectHoveredLeadId?: string | null;
    isSidebarOpen?: boolean;
    isChatOpen?: boolean;
}

export const FloatingToolbar: React.FC<FloatingToolbarProps> = (props) => {
    if (props.isProspectingMode) {
        return (
            <ProspectingToolbar
                prospectCoords={props.prospectCoords}
                prospectRadiusKm={props.prospectRadiusKm}
                onProspectRadiusChange={props.onProspectRadiusChange}
                onProspectGeolocate={props.onProspectGeolocate}
                prospectGeoLoading={props.prospectGeoLoading}
                onProspectSearch={props.onProspectSearch}
                onProspectStop={props.onProspectStop}
                prospectSearching={props.prospectSearching}
                prospectSession={props.prospectSession}
                prospectLeadsCount={props.prospectLeadsCount}
                prospectTierACount={props.prospectTierACount}
                prospectError={props.prospectError}
                prospectCityName={props.prospectCityName}
                onProspectCepLookup={props.onProspectCepLookup}
                prospectSelectedLead={props.prospectSelectedLead}
                prospectPendingLeads={props.prospectPendingLeads}
                onProspectSelectLead={props.onProspectSelectLead}
                prospectHoveredLeadId={props.prospectHoveredLeadId}
                onProspectApproveLead={props.onProspectApproveLead}
                onProspectRejectLead={props.onProspectRejectLead}
                onProspectCloseLead={props.onProspectCloseLead}
                prospectCep={props.prospectCep}
                onProspectCepChange={props.onProspectCepChange}
                isSidebarOpen={props.isSidebarOpen}
                isChatOpen={props.isChatOpen}
            />
        );
    }

    return (
        <NormalToolbar
            error={props.error}
            handleSearch={props.handleSearch}
            cnpj={props.cnpj}
            setCnpj={props.setCnpj}
            confirmedBrand={props.confirmedBrand}
            setConfirmedBrand={props.setConfirmedBrand}
            confirmedLogo={props.confirmedLogo}
            confirmedFollowers={props.confirmedFollowers}
            domainTarget={props.domainTarget}
            setDomainTarget={props.setDomainTarget}
            productFocus={props.productFocus}
            setProductFocus={props.setProductFocus}
            areaFocus={props.areaFocus}
            setAreaFocus={props.setAreaFocus}
            handleAutoEnrich={props.handleAutoEnrich}
            enrichingIds={props.enrichingIds}
            discovering={props.discovering}
            loading={props.loading}
            step={props.step}
            brandOptions={props.brandOptions}
            onBrandSelect={props.onBrandSelect}
            hasMapping={props.hasMapping}
            stopHierarchyScan={props.stopHierarchyScan}
            cancelDiscovery={props.cancelDiscovery}
            onApproveCandidate={props.onApproveCandidate}
            onRejectCandidate={props.onRejectCandidate}
            isSidebarOpen={props.isSidebarOpen}
            isChatOpen={props.isChatOpen}
        />
    );
};
