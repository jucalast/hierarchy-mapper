import React, { useEffect, useRef } from 'react';
import styles from '../ChatPanel.module.css';

interface AudioWaveformProps {
    analyserNode: React.MutableRefObject<AnalyserNode | null>;
    isActive: boolean;
}

export const AudioWaveform: React.FC<AudioWaveformProps> = ({ analyserNode, isActive }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const rafRef = useRef<number>(0);

    // Mantém canvas com o tamanho real do container (evita blur em displays HiDPI)
    useEffect(() => {
        const container = containerRef.current;
        const canvas = canvasRef.current;
        if (!container || !canvas) return;

        const ro = new ResizeObserver(entries => {
            const { width, height } = entries[0].contentRect;
            const dpr = window.devicePixelRatio || 1;
            canvas.width = width * dpr;
            canvas.height = height * dpr;
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            const ctx = canvas.getContext('2d');
            if (ctx) ctx.scale(dpr, dpr);
        });
        ro.observe(container);
        return () => ro.disconnect();
    }, []);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const BAR_W = 2.5;
        const GAP = 2;

        const draw = () => {
            rafRef.current = requestAnimationFrame(draw);

            // Lê dimensões CSS reais (não pixels do device)
            const W = parseFloat(canvas.style.width || String(canvas.width));
            const H = parseFloat(canvas.style.height || String(canvas.height));
            if (!W || !H) return;

            ctx.clearRect(0, 0, W, H);

            const analyser = analyserNode.current;
            const barCount = Math.floor(W / (BAR_W + GAP));

            if (!analyser || !isActive) {
                // Estado idle: barras baixas com ondulação suave
                const t = Date.now() / 700;
                for (let i = 0; i < barCount; i++) {
                    const h = 2.5 + Math.sin(t + i * 0.45) * 1.5;
                    const x = i * (BAR_W + GAP);
                    const y = H / 2 - h / 2;
                    ctx.fillStyle = 'rgba(255,255,255,0.18)';
                    ctx.beginPath();
                    ctx.roundRect(x, y, BAR_W, h, 1);
                    ctx.fill();
                }
                return;
            }

            const bufLen = analyser.frequencyBinCount;
            const data = new Uint8Array(bufLen);
            analyser.getByteFrequencyData(data);

            // Usa apenas a metade inferior do espectro (mais relevante para voz)
            const useBins = Math.min(barCount, Math.floor(bufLen * 0.6));

            for (let i = 0; i < barCount; i++) {
                // Interpolação: mapeia as barras visíveis nos bins disponíveis
                const binIdx = Math.floor((i / barCount) * useBins);
                const v = data[binIdx] / 255;
                const barH = Math.max(2.5, v * H * 0.9);
                const x = i * (BAR_W + GAP);
                const y = (H - barH) / 2;

                // Opacidade mais alta no meio do espectro visual
                const center = Math.abs(i / barCount - 0.5) * 2; // 0 no centro, 1 nas bordas
                const alpha = 0.55 + (1 - center) * 0.45;
                ctx.fillStyle = `rgba(255,255,255,${alpha.toFixed(2)})`;

                ctx.beginPath();
                ctx.roundRect(x, y, BAR_W, barH, 1.5);
                ctx.fill();
            }
        };

        draw();
        return () => cancelAnimationFrame(rafRef.current);
    }, [analyserNode, isActive]);

    return (
        <div ref={containerRef} className={styles.waveformContainer}>
            <canvas ref={canvasRef} style={{ display: 'block' }} />
        </div>
    );
};
