import React, { useState } from 'react';
import { Plus, X } from 'lucide-react';
import styles from '../../styles/PreferencesView.module.css';

interface StringListEditorProps {
    list: string[];
    onChange: (newList: string[]) => void;
    label: string;
    placeholder?: string;
    description?: string;
}

export const StringListEditor: React.FC<StringListEditorProps> = ({ list, onChange, label, placeholder, description }) => {
    const [inputValue, setInputValue] = useState('');

    const handleAdd = () => {
        if (inputValue.trim() && !list.includes(inputValue.trim())) {
            onChange([...list, inputValue.trim()]);
            setInputValue('');
        }
    };

    const handleRemove = (index: number) => {
        onChange(list.filter((_, i) => i !== index));
    };

    return (
        <div className={styles.formGroup} style={{ gap: '8px' }}>
            <label className={styles.label}>{label}</label>
            {description && (
                <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.35)', marginTop: '-2px', marginBottom: '4px', lineHeight: '1.4' }}>
                    {description}
                </span>
            )}
            <div style={{ display: 'flex', gap: '8px' }}>
                <input
                    type="text"
                    className={styles.select}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(); } }}
                    placeholder={placeholder || 'Adicionar item...'}
                    style={{ flex: 1 }}
                />
                <button
                    type="button"
                    onClick={handleAdd}
                    className={styles.saveBtn}
                    style={{ padding: '0 18px', borderRadius: '6px', height: '46px' }}
                >
                    <Plus size={16} />
                </button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '6px' }}>
                {list.map((item, idx) => (
                    <div
                        key={idx}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '8px',
                            backgroundColor: 'rgba(255,255,255,0.03)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: '4px', padding: '6px 12px',
                            fontSize: '12px', color: 'rgba(255,255,255,0.85)',
                        }}
                    >
                        <span>{item}</span>
                        <X size={14} onClick={() => handleRemove(idx)} style={{ color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center' }} />
                    </div>
                ))}
                {list.length === 0 && (
                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>Nenhum item adicionado.</span>
                )}
            </div>
        </div>
    );
};
