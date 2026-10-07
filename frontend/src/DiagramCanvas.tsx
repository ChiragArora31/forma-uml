import { useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, Scan, Move } from 'lucide-react';

export default function DiagramCanvas({ svg, label }: { svg: string; label: string }) {
  const root = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const src = useMemo(() => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`, [svg]);
  function fit() {
    const el = root.current;
    const img = image.current;
    if (!el || !img || !img.naturalWidth) return;
    setScale(
      Math.min(
        (el.clientWidth - 70) / img.naturalWidth,
        (el.clientHeight - 85) / img.naturalHeight,
        1.2,
      ),
    );
    setPosition({ x: 0, y: 0 });
  }
  useEffect(() => {
    const observer = new ResizeObserver(fit);
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, [svg]);
  return (
    <div
      className="canvas-body"
      ref={root}
      aria-label={`${label} diagram canvas`}
      role="region"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        const directions: Record<string, [number, number]> = {
          ArrowLeft: [40, 0],
          ArrowRight: [-40, 0],
          ArrowUp: [0, 40],
          ArrowDown: [0, -40],
        };
        if (directions[e.key]) {
          e.preventDefault();
          const [x, y] = directions[e.key];
          setPosition((p) => ({ x: p.x + x, y: p.y + y }));
        }
        if (e.key === '+' || e.key === '=') {
          e.preventDefault();
          setScale((s) => Math.min(4, s * 1.2));
        }
        if (e.key === '-') {
          e.preventDefault();
          setScale((s) => Math.max(0.1, s / 1.2));
        }
        if (e.key === '0') {
          e.preventDefault();
          fit();
        }
      }}
      onPointerDown={(e) => {
        if (e.button !== 0 || (e.target as HTMLElement).closest('button')) return;
        drag.current = { x: e.clientX, y: e.clientY, px: position.x, py: position.y };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (drag.current)
          setPosition({
            x: drag.current.px + e.clientX - drag.current.x,
            y: drag.current.py + e.clientY - drag.current.y,
          });
      }}
      onPointerUp={() => {
        drag.current = null;
      }}
      onPointerCancel={() => {
        drag.current = null;
      }}
    >
      <div
        className="diagram-image"
        style={{ transform: `translate(${position.x}px, ${position.y}px) scale(${scale})` }}
      >
        <img ref={image} src={src} alt={`${label} UML diagram`} draggable={false} onLoad={fit} />
      </div>
      <span className="pan-hint">
        <Move size={12} /> Drag or use arrow keys to explore
      </span>
      <div className="zoom-controls">
        <button aria-label="Zoom out" onClick={() => setScale((s) => Math.max(0.1, s / 1.2))}>
          <Minus size={15} />
        </button>
        <span>{Math.round(scale * 100)}%</span>
        <button aria-label="Zoom in" onClick={() => setScale((s) => Math.min(4, s * 1.2))}>
          <Plus size={15} />
        </button>
        <span className="control-divider" />
        <button aria-label="Fit diagram to canvas" onClick={fit}>
          <Scan size={16} />
        </button>
      </div>
    </div>
  );
}
