"use client";

import React, { useEffect, useState } from 'react';
import { Database } from 'lucide-react';
import styles from './Footer.module.css';
import { communication } from '@/services/api';
import { Spinner } from './ui';

const Footer: React.FC = () => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [contactCount, setContactCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const checkStatus = async () => {
      try {
        const data = await communication.getEmailCacheStatus();
        if (cancelled) return;
        setIsSyncing(Boolean(data.is_syncing));
        setContactCount(Number(data.count ?? 0));
      } catch {
        // Silencioso quando o serviço de email/cache estiver offline.
      }
    };

    checkStatus();
    const interval = window.setInterval(checkStatus, 60000); // Reduzido de 5s → 60s: status raramente muda
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.section}>
          <span className={styles.brand}>LINKB2B</span>
          <span className={styles.separator}>•</span>
          <span className={styles.legal}>© 2026 INTELLIGENCE ECOSYSTEM</span>
        </div>

        <div className={styles.section}>
          {isSyncing ? (
            <div className={styles.syncStatus}>
              <Spinner size={11} inline />
              <span>SYNCING OUTLOOK...</span>
            </div>
          ) : (
            <div className={styles.dbStatus}>
              <Database size={10} className={styles.dbIcon} />
              <span className={styles.value}>{contactCount} CONTACTS CACHED</span>
            </div>
          )}
        </div>
      </div>
    </footer>
  );
};

export default Footer;
