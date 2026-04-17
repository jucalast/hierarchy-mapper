"use client";

import React, { useState, useEffect } from 'react';
import { Loader2, Database } from 'lucide-react';
import styles from './Footer.module.css';

const Footer: React.FC = () => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [contactCount, setContactCount] = useState(0);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const response = await fetch('http://localhost:8002/api/email/cache-status');
        if (response.ok) {
          const data = await response.json();
          setIsSyncing(data.is_syncing);
          setContactCount(data.count);
        }
      } catch (e) {
        // Silencioso se o serviço estiver offline
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 5000); // Polling a cada 5s
    return () => clearInterval(interval);
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
              <Loader2 className={styles.spinner} size={11} />
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
