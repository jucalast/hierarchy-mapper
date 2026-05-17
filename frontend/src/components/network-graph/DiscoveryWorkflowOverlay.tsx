import React from 'react';
import { FloatingToolbar } from './FloatingToolbar';
import styles from './styles/HumanAnalysis.module.css';

interface DiscoveryWorkflowOverlayProps {
    error: string | null;
    handleSearch: (e?: React.FormEvent) => void;
    cnpj: string;
    setCnpj: (v: string) => void;
    confirmedBrand: string;
    setConfirmedBrand: (v: string) => void;
    confirmedLogo: string;
    setConfirmedLogo: (v: string) => void;
    confirmedFollowers: string;
    setConfirmedFollowers: (v: string) => void;
    domainTarget: string;
    setDomainTarget: (v: string) => void;
    productFocus: string;
    setProductFocus: (v: string) => void;
    areaFocus: "compras" | "logistica";
    setAreaFocus: (v: "compras" | "logistica") => void;
    handleAutoEnrich: () => void;
    enrichingIds: Set<number>;
    discovering: boolean;
    loading: boolean;
    step: "input" | "confirm" | "scanning" | "loading" | "initial";
    brandOptions: any[];
    onBrandSelect: (brand: any) => void;
    hasMapping: boolean;
    stopHierarchyScan: () => void;
    cancelDiscovery: () => void;
    activeJobId: string | null;
    showDrawer: boolean;
    showChat: boolean;
    approveCandidate: (id: string) => void;
    rejectCandidate: (id: string) => void;
    humanAnalysisContent?: React.ReactNode;
}

export const DiscoveryWorkflowOverlay: React.FC<DiscoveryWorkflowOverlayProps> = ({
    error, handleSearch, cnpj, setCnpj, confirmedBrand, setConfirmedBrand,
    confirmedLogo, setConfirmedLogo, confirmedFollowers, setConfirmedFollowers,
    domainTarget, setDomainTarget, productFocus, setProductFocus, areaFocus, setAreaFocus,
    handleAutoEnrich, enrichingIds, discovering, loading, step, brandOptions,
    onBrandSelect, hasMapping, stopHierarchyScan, cancelDiscovery, activeJobId,
    showDrawer, showChat, approveCandidate, rejectCandidate, humanAnalysisContent
}) => {
    return (
        <div className={styles.bottomToolbarRow}>
            <FloatingToolbar
                error={error}
                handleSearch={handleSearch}
                cnpj={cnpj}
                setCnpj={setCnpj}
                confirmedBrand={confirmedBrand}
                setConfirmedBrand={setConfirmedBrand}
                confirmedLogo={confirmedLogo}
                setConfirmedLogo={setConfirmedLogo}
                confirmedFollowers={confirmedFollowers}
                setConfirmedFollowers={setConfirmedFollowers}
                domainTarget={domainTarget}
                setDomainTarget={setDomainTarget}
                productFocus={productFocus}
                setProductFocus={setProductFocus}
                areaFocus={areaFocus}
                setAreaFocus={setAreaFocus}
                handleAutoEnrich={handleAutoEnrich}
                enrichingIds={enrichingIds}
                discovering={discovering}
                loading={loading}
                step={step}
                brandOptions={brandOptions}
                onBrandSelect={onBrandSelect}
                hasMapping={hasMapping}
                stopHierarchyScan={stopHierarchyScan}
                cancelDiscovery={cancelDiscovery}
                activeJobId={activeJobId}
                isSidebarOpen={showDrawer}
                isChatOpen={showChat}
                onApproveCandidate={approveCandidate}
                onRejectCandidate={rejectCandidate}
            >
                {humanAnalysisContent}
            </FloatingToolbar>
        </div>
    );
};
