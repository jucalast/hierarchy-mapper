import React, { useState, useEffect, useRef } from 'react';
import { MoreHorizontal, MoreVertical } from 'lucide-react';
import styles from './Dropdown.module.css';

export interface DropdownItem {
  label: string | React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  icon?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
  danger?: boolean;
}

interface DropdownProps {
  items: DropdownItem[];
  iconType?: 'horizontal' | 'vertical';
  align?: 'left' | 'right';
  triggerClassName?: string;
  menuClassName?: string;
  iconSize?: number;
  title?: string;
}

export const Dropdown: React.FC<DropdownProps> = ({
  items,
  iconType = 'horizontal',
  align = 'right',
  triggerClassName = '',
  menuClassName = '',
  iconSize = 16,
  title = 'Mais opções'
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    // Use capture to prevent events from conflicting with target clicks
    document.addEventListener('click', handleOutsideClick, true);
    return () => {
      document.removeEventListener('click', handleOutsideClick, true);
    };
  }, [isOpen]);

  const toggleDropdown = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setIsOpen(!isOpen);
  };

  return (
    <div className={`${styles.dropdownContainer} nodrag`} ref={containerRef}>
      <button
        onClick={toggleDropdown}
        className={`${styles.triggerBtn} ${triggerClassName} ${isOpen ? styles.active : ''}`}
        title={title}
        type="button"
      >
        {iconType === 'horizontal' ? (
          <MoreHorizontal size={iconSize} />
        ) : (
          <MoreVertical size={iconSize} />
        )}
      </button>

      {isOpen && (
        <div 
          className={`${styles.dropdownMenu} ${styles[align]} ${menuClassName}`}
          onClick={(e) => e.stopPropagation()}
        >
          {items.map((item, idx) => (
            <button
              key={idx}
              className={`${styles.dropdownItem} ${item.danger ? styles.danger : ''} ${item.className || ''}`}
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                item.onClick(e);
                setIsOpen(false);
              }}
              style={item.style}
              type="button"
            >
              {item.icon && <span className={styles.itemIcon}>{item.icon}</span>}
              <span className={styles.itemLabel}>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
