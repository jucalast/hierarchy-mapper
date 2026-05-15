import React from 'react';
import { Package, Save, RefreshCw, Plus, Edit3, Trash2, X } from 'lucide-react';
import { StringListEditor } from '../shared/StringListEditor';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'productsList'
    | 'showProductForm' | 'setShowProductForm'
    | 'editingProductIdx' | 'setEditingProductIdx'
    | 'prodName' | 'setProdName'
    | 'prodDesc' | 'setProdDesc'
    | 'prodUseCases' | 'setProdUseCases'
    | 'saving' | 'handleSaveProducts'
    | 'handleAddOrUpdateProduct' | 'handleEditProduct' | 'handleDeleteProduct'
> & { showToast: (type: 'success' | 'error', msg: string) => void };

export const ProductsTab: React.FC<Props> = ({
    productsList,
    showProductForm, setShowProductForm,
    editingProductIdx, setEditingProductIdx,
    prodName, setProdName,
    prodDesc, setProdDesc,
    prodUseCases, setProdUseCases,
    saving, handleSaveProducts,
    handleAddOrUpdateProduct, handleEditProduct, handleDeleteProduct,
    showToast,
}) => (
    <div className={styles.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 className={styles.cardTitle} style={{ margin: 0 }}>
                <span className={styles.cardTitleText}>
                    <Package size={18} /> Catálogo de Produtos e Serviços Ofertados
                </span>
            </h2>
            {!showProductForm && (
                <button
                    onClick={() => { setEditingProductIdx(null); setProdName(''); setProdDesc(''); setProdUseCases([]); setShowProductForm(true); }}
                    className={styles.saveBtn}
                    style={{ padding: '8px 16px', fontSize: '12px' }}
                >
                    <Plus size={14} /> Adicionar Produto
                </button>
            )}
        </div>

        {showProductForm && (
            <div style={{ padding: '24px', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.01)', display: 'flex', flexDirection: 'column', gap: '16px', animation: 'fadeIn 0.2s ease' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 500, color: '#fff', margin: 0, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{editingProductIdx !== null ? "Editar Produto" : "Novo Produto"}</span>
                    <X size={16} style={{ cursor: 'pointer', opacity: 0.5 }} onClick={() => setShowProductForm(false)} />
                </h3>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Nome do Produto / Serviço</label>
                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                        O nome comercial do item ou serviço oferecido.
                    </span>
                    <input type="text" className={styles.select} value={prodName} onChange={(e) => setProdName(e.target.value)} placeholder="Ex: Caixas de Papelão Ondulado" />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Descrição Completa (Utilizada pela IA em ganchos)</label>
                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                        Especificações técnicas, benefícios e materiais.
                    </span>
                    <textarea className={styles.select} rows={4} value={prodDesc} onChange={(e) => setProdDesc(e.target.value)} placeholder="Descreva as especificações, materiais e finalidade..." style={{ fontFamily: 'inherit', resize: 'vertical' }} />
                </div>

                <StringListEditor
                    list={prodUseCases}
                    onChange={setProdUseCases}
                    label="Casos de Uso / Aplicações Típicas"
                    placeholder="Ex: Kitting de linha de montagem automotiva"
                    description="Aplicações práticas ou cenários de uso do produto."
                />

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                    <button type="button" className={styles.backBtn} onClick={() => setShowProductForm(false)}>Cancelar</button>
                    <button
                        type="button"
                        className={styles.saveBtn}
                        onClick={() => handleAddOrUpdateProduct((msg) => showToast('error', msg))}
                        style={{ padding: '8px 20px', borderRadius: '4px' }}
                    >
                        {editingProductIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                    </button>
                </div>
            </div>
        )}

        <div className={styles.providersList}>
            {productsList.map((prod, idx) => (
                <div key={idx} className={styles.providerCard} style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, paddingRight: '20px' }}>
                        <h4 style={{ fontSize: '15px', color: '#fff', fontWeight: 600, margin: '0 0 6px 0' }}>{prod.name}</h4>
                        <p style={{ fontSize: '13px', opacity: 0.7, lineHeight: '1.6', fontWeight: 300, margin: '0 0 12px 0' }}>{prod.description}</p>
                        {prod.use_cases && prod.use_cases.length > 0 && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {prod.use_cases.map((uc: string, uIdx: number) => (
                                    <span key={uIdx} style={{ fontSize: '10px', backgroundColor: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', color: '#3b82f6', padding: '3px 8px', borderRadius: '4px' }}>
                                        {uc}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button onClick={() => handleEditProduct(idx)} className={styles.backBtn} style={{ padding: '6px' }} title="Editar"><Edit3 size={15} /></button>
                        <button onClick={() => handleDeleteProduct(idx)} className={styles.backBtn} style={{ padding: '6px', color: '#ef4444' }} title="Deletar"><Trash2 size={15} /></button>
                    </div>
                </div>
            ))}
            {productsList.length === 0 && (
                <div className={styles.noDataText}>O catálogo de produtos está vazio. Adicione um novo produto acima.</div>
            )}
        </div>

        <button className={styles.saveBtn} onClick={handleSaveProducts} disabled={saving} style={{ marginTop: '16px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Catálogo de Produtos"}
        </button>
    </div>
);
