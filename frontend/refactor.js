const fs = require('fs');

let c = fs.readFileSync('c:\\Users\\João Luccas\\Desktop\\LINKB2B\\hierarchy-mapper\\frontend\\src\\components\\chat\\ChatPanel.tsx', 'utf8');

c = c.replace(/if \(abortControllerRef\.current\) \{\s*abortControllerRef\.current\.abort\(\);\s*abortControllerRef\.current = null;\s*\}/g, 
\const tId = typeof threadId !== 'undefined' ? threadId : (activeThreadIdRef.current || 'global');
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
            delete abortControllersRef.current[tId];
        }\);

c = c.replace(/if \(abortControllerRef\.current\) \{\s*abortControllerRef\.current\.abort\(\);\s*\}/g,
\const tId = typeof threadId !== 'undefined' ? threadId : (activeThreadIdRef.current || 'global');
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
        }\);

c = c.replace(/const controller = new AbortController\(\);\s*abortControllerRef\.current = controller;/g,
\const controller = new AbortController();
        abortControllersRef.current[tId] = controller;\);

c = c.replace(/if \(abortControllerRef\.current === controller\) \{\s*abortControllerRef\.current = null;\s*\}/g,
\if (abortControllersRef.current[tId] === controller) {
                delete abortControllersRef.current[tId];
            }\);

fs.writeFileSync('c:\\Users\\João Luccas\\Desktop\\LINKB2B\\hierarchy-mapper\\frontend\\src\\components\\chat\\ChatPanel.tsx', c);
console.log('done');
