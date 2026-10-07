import { ArrowRight } from 'lucide-react';
import type { CatalogEntry, DiagramKind } from './types';
const DEFAULT_TYPES: DiagramKind[] = ['sequence', 'component'];
export default function DiagramPicker({
  catalog,
  selected,
  onChange,
  onDone,
}: {
  catalog: CatalogEntry[];
  selected: DiagramKind[];
  onChange: (selected: DiagramKind[]) => void;
  onDone: () => void;
}) {
  function toggleType(kind: DiagramKind) {
    onChange(selected.includes(kind) ? selected.filter((x) => x !== kind) : [...selected, kind]);
  }
  return (
    <>
      <span className="eyebrow">CHOOSE YOUR PERSPECTIVES</span>
      <h2 id="modal-title">See the whole system.</h2>
      <p>Start with sequence and component. Add detail where it helps.</p>
      <div className="catalog-actions">
        <button onClick={() => onChange(catalog.map((d) => d.id))}>Select all 14</button>
        <button onClick={() => onChange(DEFAULT_TYPES)}>Recommended pair</button>
        <span>{selected.length} selected</span>
      </div>
      {['structure', 'behavior', 'interaction'].map((category) => (
        <div className="catalog-group" key={category}>
          <h3>
            {category === 'interaction' ? 'Interaction · behavior subset' : `${category} diagrams`}
          </h3>
          <div className="catalog-grid">
            {catalog
              .filter((d) => d.category === category)
              .map((d) => (
                <label
                  className={`catalog-item ${selected.includes(d.id) ? 'selected' : ''}`}
                  key={d.id}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(d.id)}
                    onChange={() => toggleType(d.id)}
                  />
                  <span>
                    <strong>{d.label}</strong>
                    <small>{d.description}</small>
                  </span>
                </label>
              ))}
          </div>
        </div>
      ))}
      <div className="modal-footer">
        <span>
          {!selected.length
            ? 'Choose at least one diagram.'
            : 'Applies to your next design request.'}
        </span>
        <button className="primary" disabled={!selected.length} onClick={() => onDone()}>
          Use {selected.length} view{selected.length === 1 ? '' : 's'}
          <ArrowRight size={15} />
        </button>
      </div>
    </>
  );
}
