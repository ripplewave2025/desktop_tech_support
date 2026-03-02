import { useEffect, useRef } from 'react';
import {
    ArrowUp, ArrowDown, ArrowLeft, ArrowRight, X,
} from 'lucide-react';

export function PinMenu({ onSelect, onClose }) {
    const ref = useRef(null);

    // Close on outside click
    useEffect(() => {
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) {
                onClose();
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [onClose]);

    return (
        <div className="pin-menu" ref={ref}>
            <button
                className="pin-menu-btn"
                onClick={() => onSelect('top')}
                title="Pin to top"
            >
                <ArrowUp />
            </button>
            <button
                className="pin-menu-btn"
                onClick={() => onSelect('bottom')}
                title="Pin to bottom"
            >
                <ArrowDown />
            </button>
            <button
                className="pin-menu-btn"
                onClick={() => onSelect('left')}
                title="Pin to left"
            >
                <ArrowLeft />
            </button>
            <button
                className="pin-menu-btn"
                onClick={() => onSelect('right')}
                title="Pin to right"
            >
                <ArrowRight />
            </button>
            <button
                className="pin-menu-btn"
                onClick={() => onSelect('none')}
                title="Unpin"
            >
                <X />
            </button>
        </div>
    );
}
