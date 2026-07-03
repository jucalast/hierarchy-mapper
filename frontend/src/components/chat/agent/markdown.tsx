import React from 'react';

// Função auxiliar para converter marcação markdown básica (negrito, itálico, listas) para HTML
export function parseMarkdownToHTML(text: string): string {
    if (!text) return '';
    let html = text;
    // Bold (support multiline)
    html = html.replace(/\*\*([\s\S]*?)\*\*/g, '<b>$1</b>');
    // Italic (support multiline, not matching **)
    html = html.replace(/(^|[^\*])\*([^\*]+)\*(?!\*)/g, '$1<i>$2</i>');

    // Lists
    const lines = html.split('\n');
    let inList = false;
    let parsedLines = [];
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];
        // Match * item or - item
        const listMatch = line.match(/^[\*\-]\s+(.*)/);
        if (listMatch) {
            if (!inList) {
                parsedLines.push('<ul style="margin-top: 4px; margin-bottom: 4px; padding-left: 20px;">');
                inList = true;
            }
            parsedLines.push(`<li>${listMatch[1]}</li>`);
        } else {
            if (inList) {
                parsedLines.push('</ul>');
                inList = false;
            }
            parsedLines.push(line);
        }
    }
    if (inList) parsedLines.push('</ul>');
    return parsedLines.join('\n');
}

export const renderInline = (text: string): React.ReactNode[] =>
    text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith('`') && part.endsWith('`')) {
            const inner = part.slice(1, -1);
            return (
                <span key={i} style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    background: 'var(--sw-hover)',
                    color: 'var(--sw-text-base)',
                    fontSize: '0.85em',
                    fontWeight: 500,
                    margin: '0 2px',
                    fontFamily: 'monospace',
                    verticalAlign: 'baseline',
                    lineHeight: '1.4'
                }}>
                    {inner}
                </span>
            );
        }
        return part as any;
    });

export const renderMarkdown = (text: string): React.ReactNode => {
    if (!text) return null;
    return text.split('\n').map((line, idx) => {
        if (line.trim() === '---')
            return <hr key={idx} style={{ margin: '10px 0', border: 'none', borderTop: 'var(--sw-border-width) solid var(--sw-border)' }} />;
        if (line.startsWith('### '))
            return <h3 key={idx} style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(4))}</h3>;
        if (line.startsWith('## '))
            return <h3 key={idx} style={{ fontSize: '16px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(3))}</h3>;

        let trimmed = line.trim();
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
            return (
                <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '4px', marginLeft: '12px' }}>
                    <span style={{ opacity: 0.6 }}>•</span>
                    <div>{renderInline(trimmed.slice(2))}</div>
                </div>
            );
        }

        return <div key={idx} style={{ marginBottom: '10px', lineHeight: '1.65' }}>{renderInline(line)}</div>;
    });
};
