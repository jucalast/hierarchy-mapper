import React from 'react';
import { Sidebar } from '../layout/Sidebar';
import { Drawer } from '../ui/Drawer';
import { Header } from '../layout/Header';
import { GraphCanvas } from './GraphCanvas';
import { HierarchyDiscoveryOverlay } from './HierarchyDiscoveryOverlay';
import { MessagesView } from '../messages/MessagesView';
import { LigacaoView } from '../ligacao/LigacaoView';
import { ProspectingView } from '../prospecting/ProspectingView';
import { PreferencesView } from '../layout/PreferencesView';
import { HierarchyScanView } from '../hierarchy-scan/HierarchyScanView';
import { ModelSelector } from '../chat/ModelSelector';
import { NotificationContainer } from '../ui/Notification';
import type { NotificationType } from '../ui/Notification';
import { ConfirmModal } from '../ui/ConfirmModal';
import { EmployeeDetailsModal } from './components/EmployeeDetailsModal';
import { FloatingToolbar } from './FloatingToolbar';
import { ScanTerminalPanel } from './components/ScanTerminalPanel';
import { ScanPreviewBubble } from './components/ScanPreviewBubble';
import { getAvatarUrl } from '../../utils/avatarUtils';

import graphStyles from './styles/Graph.module.css';
import haStyles from './styles/HumanAnalysis.module.css';
import sidebarStyles from '../layout/Sidebar.module.css';
import headerStyles from '../layout/Header.module.css';

const styles = { ...graphStyles, ...haStyles, ...sidebarStyles, ...headerStyles };

export interface NetworkGraphLayoutProps {
    theme: string;
    setTheme: (theme: string) => void;
    showDrawer: boolean;
    handleSetShowDrawer: (show: boolean) => void;
    activeView: string;
    setActiveView: any;
    currentUser: any;
    tasksForToday?: number;
    onToggleChat: any;
    onLogout: any;
    handleNewCompany: () => void;
    refineHierarchy: (rawEmployees: any[]) => void;
    smartSyncPipedrive: any;
    hierarchy: any; // return from useHierarchy
    discovery: any; // return from useDiscoveryWorkflow
    scan: any; // scan state
    isScanForCurrentOrg: boolean;
    filteredOrgs: any[];
    loadingOrgs: boolean;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    handleOrgClick: (org: any, openChat?: boolean) => void;
    currentOrgId: number | null | undefined;
    handleOrgRenamed: any;
    confirmedLogo: string;
    activeJobId: string | null;
    rawEmployees: any[];
    pipedriveOrgs: any[];
    addNotification: (type: NotificationType, message: string) => void;
    handleOrgReset: (orgId: number) => void;
    setEditEmployeeModal: (val: any) => void;
    uniqueStages: any[];
    activeStageFilter: any;
    setActiveStageFilter: (val: any) => void;
    confirmedBrand: string;
    unreadCount: number;
    notifications: any[];
    removeNotification: any;
    nodes: any[];
    edges: any[];
    onNodesChange: any;
    onEdgesChange: any;
    onConnect: any;
    shouldFitView: boolean;
    setShouldFitView: (val: boolean) => void;
    handleSearchOrScan: () => void;
    handleAutoEnrich: () => void;
    enrichingIds: Set<number>;
    stopHierarchyScan: (notifyFn: any) => void;
    cancelDiscovery: () => void;
    approveCandidate: (id: string) => Promise<any>;
    setConfirmModal: (val: any) => void;
    previewExpanded: boolean;
    setPreviewExpanded: (val: any) => void;
    selectedModel: string;
    setSelectedModel: (val: string) => void;
    strictMode: boolean;
    setStrictMode: (val: boolean) => void;
    confirmModal: any;
    editEmployeeModal: any;
    ligacaoData: any;
    prospecting: any;
    fetchPipedriveOrgs: () => void;
    mappingMode: any;
    setMappingMode: any;
    confirmedLinkedInUrl: string;
    areaFocus: string;
    productFocus: string;
    SmartBackground: React.FC;
    FitViewHandler: React.FC<any>;
}

export function NetworkGraphLayout(props: NetworkGraphLayoutProps) {
    const {
        theme, setTheme, showDrawer, handleSetShowDrawer, activeView, setActiveView,
        currentUser, tasksForToday, onToggleChat, onLogout, handleNewCompany,
        refineHierarchy, smartSyncPipedrive, hierarchy, discovery, scan, isScanForCurrentOrg,
        filteredOrgs, loadingOrgs, searchTerm, setSearchTerm, handleOrgClick, currentOrgId,
        handleOrgRenamed, confirmedLogo, activeJobId, rawEmployees, pipedriveOrgs,
        addNotification, handleOrgReset, setEditEmployeeModal, uniqueStages, activeStageFilter,
        setActiveStageFilter, confirmedBrand, unreadCount, notifications, removeNotification,
        nodes, edges, onNodesChange, onEdgesChange, onConnect, shouldFitView, setShouldFitView,
        handleSearchOrScan, handleAutoEnrich, enrichingIds, stopHierarchyScan, cancelDiscovery,
        approveCandidate, setConfirmModal, previewExpanded, setPreviewExpanded, selectedModel,
        setSelectedModel, strictMode, setStrictMode, confirmModal, editEmployeeModal, ligacaoData,
        prospecting, fetchPipedriveOrgs, mappingMode, setMappingMode, confirmedLinkedInUrl,
        areaFocus, productFocus, SmartBackground, FitViewHandler
    } = props;

    return (
        <div className={styles.container} data-theme={theme}>
            
            <Sidebar
                showDrawer={showDrawer}
                setShowDrawer={handleSetShowDrawer}
                theme={theme}
                onToggleTheme={() => {
                    const newTheme = theme === "dark" ? "light" : "dark";
                    setTheme(newTheme);
                    localStorage.setItem("preferred-theme", newTheme);
                    document.documentElement.setAttribute("data-theme", newTheme);
                    window.dispatchEvent(new CustomEvent('theme_changed', { detail: newTheme }));
                }}
                onReset={handleNewCompany}
                onRefine={() => {
                    let hasActiveDiscovery = false;
                    for (let _i = 0; _i < localStorage.length; _i++) {
                        if ((localStorage.key(_i) || '').startsWith('active-discovery-job-')) { hasActiveDiscovery = true; break; }
                    }
                    if (hasActiveDiscovery) {
                        addNotification('warning', "Aguarde o mapeamento atual terminar antes de utilizar o Analista de IA.");
                        return;
                    }
                    refineHierarchy(rawEmployees);
                }}
                onSmartSync={async () => {
                    await smartSyncPipedrive((type, msg) => {
                        addNotification(type, msg);
                        if (type === 'success') {
                            fetchPipedriveOrgs();
                        }
                    });
                }}
                isSmartSyncLoading={hierarchy.isSmartSyncLoading}
                onOpenProspecting={() => setActiveView(activeView === 'prospecting' ? 'graph' : 'prospecting')}
                isProspecting={activeView === 'prospecting'}
                onOpenPreferences={() => setActiveView(activeView === 'preferences' ? 'graph' : 'preferences')}
                isPreferences={activeView === 'preferences'}
                onOpenLinkedinScrape={() => setActiveView(activeView === 'linkedin-scrape' ? 'graph' : 'linkedin-scrape')}
                isLinkedinScrape={activeView === 'linkedin-scrape'}
                onOpenLigacao={() => setActiveView(activeView === 'ligacao' ? 'graph' : 'ligacao')}
                isLigacao={activeView === 'ligacao'}
                isScanActive={isScanForCurrentOrg && scan.isScanning}
                currentUser={currentUser}
                tasksForToday={tasksForToday}
                onToggleChat={onToggleChat}
                onLogout={onLogout}
            />

            <div className={styles.mainWrapper}>
                <div className={styles.contentWrapper}>
                    {activeView !== 'preferences' && activeView !== 'messages' && activeView !== 'ligacao' && (
                        <Drawer
                            showDrawer={showDrawer}
                            setShowDrawer={handleSetShowDrawer}
                            filteredOrgs={filteredOrgs}
                            isLoading={loadingOrgs}
                            searchTerm={searchTerm}
                            setSearchTerm={setSearchTerm}
                            onOrgClick={handleOrgClick}
                            selectedOrgId={currentOrgId}
                            onOrgRenamed={handleOrgRenamed}
                            selectedOrgLogo={confirmedLogo}
                            activeJobId={activeJobId}
                            graphEmployees={rawEmployees}
                            refreshDetailsTrigger={pipedriveOrgs.length}
                            addNotification={addNotification}
                            onOrgReset={handleOrgReset}
                            onEditEmployee={(id: string) => setEditEmployeeModal({ isOpen: true, empId: id })}
                            onOrgDomainChanged={(oldDomain: string, newDomain: string) => {
                                const getDomain = (url: string) => {
                                    try {
                                        return new URL(url.startsWith('http') ? url : `https://${url}`).hostname.replace(/^www\./, '');
                                    } catch {
                                        return url;
                                    }
                                };
                                const cleanOld = getDomain(oldDomain);
                                const cleanNew = getDomain(newDomain);
                                
                                rawEmployees.forEach(emp => {
                                    if (emp.email && emp.email.includes(`@${cleanOld}`)) {
                                        const newEmail = emp.email.replace(`@${cleanOld}`, `@${cleanNew}`);
                                        hierarchy.updateEmployee(emp.id, { email: newEmail });
                                    }
                                });
                            }}
                            uniqueStages={uniqueStages}
                            activeStageFilter={activeStageFilter}
                            onNavigateToRoot={handleNewCompany}
                            setActiveStageFilter={setActiveStageFilter}
                            totalOrgsCount={pipedriveOrgs.length}
                        />
                    )}

                    <div className={styles.mainContent}>
                        {activeView !== 'preferences' && activeView !== 'ligacao' && (
                            <Header
                                confirmedBrand={confirmedBrand}
                                activeView={activeView}
                                onToggleMessages={() => setActiveView(activeView === 'messages' ? 'graph' : 'messages')}
                                unreadCount={unreadCount}
                            />
                        )}
                        <NotificationContainer notifications={notifications} removeNotification={removeNotification} />

                        <div className={styles.graphWrapper}>
                            {activeView === 'graph' && (
                                <>
                                    <GraphCanvas
                                        nodes={nodes}
                                        edges={edges}
                                        onNodesChange={onNodesChange}
                                        onEdgesChange={onEdgesChange}
                                        onConnect={onConnect}
                                        fitViewHandler={<FitViewHandler shouldFitView={shouldFitView} nodes={nodes} setShouldFitView={setShouldFitView} />}
                                        smartBackground={<SmartBackground />}
                                        onCopyData={() => {
                                            const data = { nodes, edges };
                                            navigator.clipboard.writeText(JSON.stringify(data, null, 2));
                                            addNotification('info', "Dados do grafo copiados!");
                                        }}
                                        onRefine={() => {
                                            let hasActiveDiscovery = false;
                                            for (let _i = 0; _i < localStorage.length; _i++) {
                                                if ((localStorage.key(_i) || '').startsWith('active-discovery-job-')) { hasActiveDiscovery = true; break; }
                                            }
                                            if (hasActiveDiscovery) {
                                                addNotification('warning', "Aguarde o mapeamento atual terminar antes de utilizar o Analista de IA.");
                                                return;
                                            }
                                            refineHierarchy(rawEmployees);
                                        }}
                                    />
                                    
                                    <HierarchyDiscoveryOverlay
                                        error={null}
                                        handleSearch={handleSearchOrScan}
                                        cnpj={discovery.cnpj}
                                        setCnpj={discovery.setCnpj}
                                        confirmedBrand={discovery.confirmedBrand}
                                        setConfirmedBrand={discovery.setConfirmedBrand}
                                        confirmedLogo={discovery.confirmedLogo}
                                        setConfirmedLogo={discovery.setConfirmedLogo}
                                        confirmedFollowers={discovery.confirmedFollowers}
                                        setConfirmedFollowers={discovery.setConfirmedFollowers}
                                        domainTarget={discovery.domainTarget}
                                        setDomainTarget={discovery.setDomainTarget}
                                        productFocus={discovery.productFocus}
                                        setProductFocus={discovery.setProductFocus}
                                        areaFocus={discovery.areaFocus}
                                        setAreaFocus={discovery.setAreaFocus}
                                        handleAutoEnrich={handleAutoEnrich}
                                        enrichingIds={enrichingIds}
                                        discovering={hierarchy.discovering}
                                        loading={hierarchy.loading}
                                        step={discovery.step}
                                        brandOptions={hierarchy.brandOptions}
                                        onBrandSelect={discovery.handleBrandSelect}
                                        hasMapping={nodes.length > 0}
                                        stopHierarchyScan={() => stopHierarchyScan(addNotification)}
                                        cancelDiscovery={cancelDiscovery}
                                        activeJobId={activeJobId}
                                        showDrawer={showDrawer}
                                        showChat={false}
                                        approveCandidate={async (id: string) => {
                                            await approveCandidate(id);
                                            addNotification('success', "Perfil aprovado.");
                                        }}
                                        rejectCandidate={(id: string) => setConfirmModal({ isOpen: true, empId: id })}
                                        mappingMode={mappingMode}
                                        onMappingModeChange={setMappingMode}
                                        scanTerminal={
                                            isScanForCurrentOrg && scan.isScanning ? (
                                                <ScanTerminalPanel consoleLogs={scan.consoleLogs} isVisible={true} />
                                            ) : undefined
                                        }
                                        scanPreview={
                                            isScanForCurrentOrg && scan.isScanning ? (
                                                <ScanPreviewBubble
                                                    hasPreview={scan.hasPreview}
                                                    previewUrl={scan.previewUrl}
                                                    isScanning={scan.isScanning}
                                                    expanded={previewExpanded}
                                                    onToggleExpand={() => setPreviewExpanded((v: boolean) => !v)}
                                                    onImageClick={scan.handleImageClick}
                                                    onSendText={scan.sendText}
                                                    onPressEnter={scan.pressEnter}
                                                    onPressBackspace={scan.pressBackspace}
                                                    consoleLogs={scan.consoleLogs}
                                                />
                                            ) : undefined
                                        }
                                        isScanning={isScanForCurrentOrg && scan.isScanning}
                                        onStopScan={scan.stopScan}
                                        humanAnalysisContent={(() => {
                                            const pending = rawEmployees.filter(e => e.role && e.role.toLowerCase().includes('humana'));
                                            if (pending.length === 0) return null;
                                            const layerClasses = [styles.stackLayer0, styles.stackLayer1, styles.stackLayer2];
                                            return (
                                                <div
                                                    className={styles.humanAnalysisTrigger}
                                                    onClick={() => {
                                                        const isShowing = hierarchy.brandOptions.length > 0 && hierarchy.brandOptions[0]?.type === 'person';
                                                        if (isShowing) { hierarchy.setBrandOptions([]); return; }
                                                        hierarchy.setBrandOptions(pending.map((p: any) => ({
                                                            name: p.name,
                                                            logo: getAvatarUrl(p),
                                                            followers: p.department || 'Pendente',
                                                            type: 'person',
                                                            id: p.id,
                                                            originalEmployee: p,
                                                            url: p.linkedin_url || p.linkedin || p.url || undefined,
                                                        })));
                                                    }}
                                                >
                                                    <div className={styles.humanAnalysisAvatarStack}>
                                                        <div className={styles.humanAnalysisNotification}>
                                                            {pending.length}
                                                        </div>
                                                        {pending.slice(0, 3).map((p: any, i: number) => {
                                                            const avatarUrl = getAvatarUrl(p);
                                                            return (
                                                                <div
                                                                    key={p.id}
                                                                    className={`${styles.humanAnalysisStackedAvatar} ${layerClasses[i]}`}
                                                                >
                                                                    <img
                                                                        src={avatarUrl || '/imagem_linkedin.png'}
                                                                        alt={p.name}
                                                                        style={{ width: '100%', height: '100%', objectFit: 'cover', transform: avatarUrl ? 'none' : 'scale(1.6)' }}
                                                                        onError={(e) => {
                                                                             const img = e.currentTarget as HTMLImageElement;
                                                                             img.src = '/imagem_linkedin.png';
                                                                             img.style.transform = 'scale(1.6)';
                                                                        }}
                                                                    />
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    />
                                </>
                            )}

                            {activeView === 'messages' && (
                                <MessagesView key={`${location.pathname}?view=messages`} onBack={() => setActiveView('graph')} orgId={currentOrgId} />
                            )}
                            {activeView === 'ligacao' && (
                                <LigacaoView onBack={() => setActiveView('graph')} initialData={ligacaoData} />
                            )}
                            {activeView === 'prospecting' && (
                                <>
                                    <ProspectingView
                                        coords={prospecting.coords}
                                        onMapClick={prospecting.setCoords}
                                        radiusKm={prospecting.radiusKm}
                                        leads={prospecting.leads}
                                        selectedLead={prospecting.selectedLead}
                                        onLeadClick={(lead: any) => {
                                            prospecting.setSelectedLead(lead);
                                        }}
                                        onLeadClose={() => prospecting.setSelectedLead(null)}
                                        onApproveLead={prospecting.approveLead}
                                        onRejectLead={prospecting.rejectLead}
                                        session={prospecting.session}
                                    />
                                    <div className={styles.bottomToolbarRow}>
                                        <FloatingToolbar
                                            error={null}
                                            handleSearch={() => {}}
                                            cnpj=""
                                            setCnpj={() => {}}
                                            confirmedBrand=""
                                            setConfirmedBrand={() => {}}
                                            confirmedLogo=""
                                            setConfirmedLogo={() => {}}
                                            confirmedFollowers=""
                                            setConfirmedFollowers={() => {}}
                                            domainTarget=""
                                            setDomainTarget={() => {}}
                                            productFocus=""
                                            setProductFocus={() => {}}
                                            areaFocus="compras"
                                            setAreaFocus={() => {}}
                                            handleAutoEnrich={() => {}}
                                            enrichingIds={new Set()}
                                            discovering={false}
                                            loading={false}
                                            step="initial"
                                            brandOptions={[]}
                                            onBrandSelect={() => {}}
                                            isSidebarOpen={showDrawer}
                                            isChatOpen={false}
                                            
                                            // Modo Prospecção
                                            isProspectingMode={true}
                                            prospectCoords={prospecting.coords}
                                            prospectRadiusKm={prospecting.radiusKm}
                                            onProspectRadiusChange={prospecting.setRadiusKm}
                                            onProspectGeolocate={prospecting.geolocate}
                                            prospectGeoLoading={prospecting.geoLoading}
                                            onProspectSearch={prospecting.startSearch}
                                            onProspectStop={prospecting.stopSearch}
                                            prospectSearching={prospecting.searching}
                                            prospectSession={prospecting.session}
                                            prospectLeadsCount={prospecting.leads.length}
                                            prospectTierACount={prospecting.leads.filter((l: any) => l.icp_tier === 'A').length}
                                            prospectError={prospecting.error}
                                            prospectCityName={prospecting.cityName}
                                            onProspectCepLookup={prospecting.lookupCep}
                                            prospectSelectedLead={prospecting.selectedLead}
                                            prospectPendingLeads={prospecting.leads.filter((l: any) => l.status === 'pending')}
                                            onProspectSelectLead={prospecting.setSelectedLead}
                                            onProspectApproveLead={prospecting.approveLead}
                                            onProspectRejectLead={prospecting.rejectLead}
                                            onProspectCloseLead={() => prospecting.setSelectedLead(null)}
                                            prospectCep={prospecting.cep}
                                            onProspectCepChange={prospecting.setCep}
                                        />
                                    </div>
                                </>
                            )}
                            {activeView === 'preferences' && (
                                <PreferencesView onBack={() => setActiveView('graph')} />
                            )}
                            {activeView === 'linkedin-scrape' && (
                                <HierarchyScanView
                                    onBack={() => setActiveView('graph')}
                                    defaultCompanyUrl={confirmedLinkedInUrl
                                        ? (confirmedLinkedInUrl.trim().endsWith('/people/')
                                            ? confirmedLinkedInUrl.trim()
                                            : confirmedLinkedInUrl.trim().replace(/\/+$/, '') + '/people/')
                                        : ''}
                                    isScanning={isScanForCurrentOrg && scan.isScanning}
                                    scanProgress={isScanForCurrentOrg ? scan.scanProgress : 0}
                                    consoleLogs={isScanForCurrentOrg ? scan.consoleLogs : []}
                                    hasPreview={isScanForCurrentOrg && scan.hasPreview}
                                    previewUrl={isScanForCurrentOrg ? scan.previewUrl : ''}
                                    scanResults={isScanForCurrentOrg ? scan.scanResults : []}
                                    scanError={isScanForCurrentOrg ? scan.scanError : null}
                                    onStartScan={(url: string, cookie: string) => {
                                        if (currentOrgId) {
                                            scan.startScan(currentOrgId, url, cookie, areaFocus, productFocus, selectedModel);
                                        }
                                    }}
                                    onStopScan={scan.stopScan}
                                    onImageClick={scan.handleImageClick}
                                    onSendText={scan.sendText}
                                    onPressEnter={scan.pressEnter}
                                    onPressBackspace={scan.pressBackspace}
                                />
                            )}
                        </div>

                        {activeView === 'graph' && (
                            <div 
                                className="dropdownDown"
                                style={{
                                    position: 'absolute',
                                    top: '68px',
                                    right: '16px',
                                    zIndex: 10,
                                }}
                            >
                                <ModelSelector
                                    model={selectedModel as any}
                                    setModel={setSelectedModel as any}
                                    strictMode={strictMode}
                                    setStrictMode={setStrictMode}
                                    theme={theme}
                                />
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <ConfirmModal
                isOpen={confirmModal.isOpen}
                onCancel={() => setConfirmModal({ isOpen: false, empId: null })}
                onConfirm={async () => {
                    if (confirmModal.empId) {
                        await hierarchy.rejectCandidate(confirmModal.empId);
                        addNotification('info', "Perfil descartado.");
                    }
                    setConfirmModal({ isOpen: false, empId: null });
                }}
                title="Descartar Perfil"
                message="Tem certeza que deseja remover este profissional? Ele será movido para o grupo de descartados."
            />

            <EmployeeDetailsModal
                isOpen={editEmployeeModal.isOpen}
                onClose={() => setEditEmployeeModal({ isOpen: false, empId: null })}
                empId={editEmployeeModal.empId}
                rawEmployees={rawEmployees}
                handleUpdateEmployee={hierarchy.updateEmployee}
            />
        </div>
    );
}
