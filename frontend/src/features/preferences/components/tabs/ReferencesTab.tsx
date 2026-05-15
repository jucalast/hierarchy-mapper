import React from 'react';
import { Users, Save, RefreshCw, Plus, Edit3, Trash2, X } from 'lucide-react';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'referenceClients'
    | 'showClientForm' | 'setShowClientForm'
    | 'editingClientIdx' | 'setEditingClientIdx'
    | 'clientName' | 'setClientName'
    | 'clientSegment' | 'setClientSegment'
    | 'saving' | 'handleSaveReferences'
    | 'handleAddOrUpdateClient' | 'handleEditClient' | 'handleDeleteClient'
> & { showToast: (type: 'success' | 'error', msg: string) => void };

export const ReferencesTab: React.FC<Props> = ({
    referenceClients,
    showClientForm, setShowClientForm,
    editingClientIdx, setEditingClientIdx,
    clientName, setClientName,
    clientSegment, setClientSegment,
    saving, handleSaveReferences,
    handleAddOrUpdateClient, handleEditClient, handleDeleteClient,
    showToast,
}) => (
    <div className={styles.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 className={styles.cardTitle} style={{ margin: 0 }}>
                <span className={styles.cardTitleText}>
                    <Users size={18} /> Clientes de Referência (Autoridade no Outreach)
                </span>
            </h2>
            {!showClientForm && (
                <button
                    onClick={() => { setEditingClientIdx(null); setClientName(''); setClientSegment(''); setShowClientForm(true); }}
                    className={styles.saveBtn}
                    style={{ padding: '8px 16px', fontSize: '12px' }}
                >
                    <Plus size={14} /> Adicionar Cliente
                </button>
            )}
        </div>

        {showClientForm && (
            <div style={{ padding: '20px', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.01)', display: 'flex', flexDirection: 'column', gap: '14px', animation: 'fadeIn 0.2s ease' }}>
                <h3 style={{ fontSize: '13px', fontWeight: 500, color: '#fff', margin: 0, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{editingClientIdx !== null ? "Editar Cliente de Referência" : "Novo Cliente de Referência"}</span>
                    <X size={16} style={{ cursor: 'pointer', opacity: 0.5 }} onClick={() => setShowClientForm(false)} />
                </h3>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Nome do Cliente (Marca/Empresa)</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            Nome de uma marca de destaque que já seja seu cliente ativo para atuar como prova social.
                        </span>
                        <input type="text" className={styles.select} value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="Ex: Toyota TMD" />
                    </div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Segmento / Descrição de Par</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            O setor de atuação ou perfil do cliente.
                        </span>
                        <input type="text" className={styles.select} value={clientSegment} onChange={(e) => setClientSegment(e.target.value)} placeholder="Ex: Montadora automotiva" />
                    </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '6px' }}>
                    <button type="button" className={styles.backBtn} onClick={() => setShowClientForm(false)}>Cancelar</button>
                    <button
                        type="button"
                        className={styles.saveBtn}
                        onClick={() => handleAddOrUpdateClient((msg) => showToast('error', msg))}
                        style={{ padding: '8px 20px', borderRadius: '4px' }}
                    >
                        {editingClientIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                    </button>
                </div>
            </div>
        )}

        <div className={styles.providersList}>
            {referenceClients.map((client, idx) => (
                <div key={idx} className={styles.providerCard} style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h4 style={{ fontSize: '14px', color: '#fff', fontWeight: 600, margin: 0 }}>{client.name}</h4>
                        <span style={{ fontSize: '12px', opacity: 0.5, fontWeight: 300 }}>{client.segment}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button onClick={() => handleEditClient(idx)} className={styles.backBtn} style={{ padding: '6px' }} title="Editar"><Edit3 size={15} /></button>
                        <button onClick={() => handleDeleteClient(idx)} className={styles.backBtn} style={{ padding: '6px', color: '#ef4444' }} title="Deletar"><Trash2 size={15} /></button>
                    </div>
                </div>
            ))}
            {referenceClients.length === 0 && (
                <div className={styles.noDataText}>Nenhum cliente de referência cadastrado ainda.</div>
            )}
        </div>

        <button className={styles.saveBtn} onClick={handleSaveReferences} disabled={saving} style={{ marginTop: '16px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Clientes de Referência"}
        </button>
    </div>
);
