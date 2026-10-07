import type { Revision } from './types';

export function revisionChanges(previous: Revision, current: Revision) {
  const before = new Map(previous.architecture.components.map((c) => [c.id, c]));
  const after = new Map(current.architecture.components.map((c) => [c.id, c]));
  const entries = [...after.values()]
    .filter((c) => !before.has(c.id))
    .map((c) => ({ status: 'Added', name: c.name, detail: c.responsibility }));
  for (const c of before.values())
    if (!after.has(c.id))
      entries.push({ status: 'Removed', name: c.name, detail: c.responsibility });
  for (const c of after.values())
    if (before.has(c.id) && JSON.stringify(c) !== JSON.stringify(before.get(c.id)))
      entries.push({
        status: 'Changed',
        name: c.name,
        detail: `Updated ${Object.keys(c)
          .filter(
            (k) =>
              JSON.stringify((c as unknown as Record<string, unknown>)[k]) !==
              JSON.stringify((before.get(c.id) as unknown as Record<string, unknown>)[k]),
          )
          .join(', ')}. ${c.responsibility}`,
      });
  const fields: Record<string, string> = {
    requirements: 'Requirement',
    assumptions: 'Assumption',
    connections: 'Connection',
    entities: 'Domain model',
    relations: 'Domain relationship',
    actors: 'Actor',
    steps: 'Workflow',
    interactions: 'Interaction',
    states: 'State',
    transitions: 'Lifecycle',
    nodes: 'Deployment',
    stereotypes: 'Profile',
    timelines: 'Timing example',
  };
  const signature = (value: unknown) => JSON.stringify(value);
  const componentNames = new Map(
    [...previous.architecture.components, ...current.architecture.components].map((c) => [
      c.id,
      c.name,
    ]),
  );
  const entityNames = new Map(
    [...previous.architecture.entities, ...current.architecture.entities].map((c) => [
      c.id,
      c.name,
    ]),
  );
  const ref = (value: unknown, entity = false) =>
    (entity ? entityNames : componentNames).get(String(value)) ?? String(value);
  function describe(value: unknown, field: string) {
    if (typeof value === 'string') return value;
    const item = value as Record<string, unknown>;
    if (typeof item.source === 'string' && typeof item.target === 'string')
      return `${field === 'transitions' ? item.source : ref(item.source, field === 'relations')} → ${field === 'transitions' ? item.target : ref(item.target, field === 'relations')}: ${item.label ?? item.message ?? item.event ?? item.kind ?? 'relationship'}${item.guard ? `; when ${item.guard}` : ''}`;
    if (typeof item.action === 'string')
      return `${ref(item.owner)}: ${item.action}${item.guard ? `; when ${item.guard}, otherwise ${item.alternative}` : ''}`;
    if (typeof item.name === 'string') {
      if (Array.isArray(item.goals)) return `${item.name}: ${item.goals.join('; ')}`;
      if (Array.isArray(item.components))
        return `${item.name}: ${item.components.map((v) => ref(v)).join(', ')}`;
      if (Array.isArray(item.attributes))
        return `${item.name}: ${item.attributes.map((a: { name: string; type: string }) => `${a.name} (${a.type})`).join(', ')}${Array.isArray(item.operations) && item.operations.length ? `; operations: ${item.operations.join(', ')}` : ''}`;
      return `${item.name}: ${item.constraint ?? item.responsibility ?? 'design detail updated'}`;
    }
    if (Array.isArray(item.ticks))
      return `${ref(item.component)}: ${item.ticks.map((t: { time_ms: number; state: string }) => `${t.time_ms}ms ${t.state}`).join(' → ')}`;
    return 'Design details updated.';
  }
  for (const [key, name] of Object.entries(fields)) {
    const beforeItems = (previous.architecture[key] ?? []) as unknown[];
    const afterItems = (current.architecture[key] ?? []) as unknown[];
    const oldValues = new Set(beforeItems.map(signature));
    const newValues = new Set(afterItems.map(signature));
    if (
      ['steps', 'interactions', 'states'].includes(key) &&
      signature(beforeItems) !== signature(afterItems) &&
      oldValues.size === newValues.size &&
      [...oldValues].every((v) => newValues.has(v))
    )
      entries.push({
        status: 'Changed',
        name: `${name} order`,
        detail: afterItems.map((v) => describe(v, key)).join(' → '),
      });
    for (const v of afterItems)
      if (!oldValues.has(signature(v)))
        entries.push({ status: 'Added', name, detail: describe(v, key) });
    for (const v of beforeItems)
      if (!newValues.has(signature(v)))
        entries.push({ status: 'Removed', name, detail: describe(v, key) });
  }
  if (previous.architecture.summary !== current.architecture.summary)
    entries.push({
      status: 'Changed',
      name: 'Design intent',
      detail: current.architecture.summary,
    });
  return entries;
}
