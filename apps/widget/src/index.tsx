import { createRoot } from 'react-dom/client';
import { Widget } from './Widget';
import './index.css';

const init = () => {
    let scriptTag = document.currentScript as HTMLScriptElement | null;
    if (!scriptTag) {
        const scripts = document.getElementsByTagName('script');
        for (let i = 0; i < scripts.length; i++) {
            const src = scripts[i].src;
            if (src.includes('widget.js') || src.includes('index.tsx')) {
                scriptTag = scripts[i] as HTMLScriptElement;
                break;
            }
        }
    }
    
    const apiKey = scriptTag?.getAttribute('data-api-key');
    const apiBaseUrl = scriptTag?.getAttribute('data-api-base-url') || (
        scriptTag?.src ? new URL(scriptTag.src).origin : undefined
    );

    if (!apiKey) {
        console.error('ChatWidget: data-api-key attribute is missing on the script tag.');
        return;
    }

    const container = document.createElement('div');
    container.id = 'chat-widget-container';
    document.body.appendChild(container);

    const root = createRoot(container);
    root.render(<Widget apiKey={apiKey} apiBaseUrl={apiBaseUrl} />);
};

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    init();
} else {
    window.addEventListener('DOMContentLoaded', init);
}
