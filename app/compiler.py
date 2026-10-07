"""Pure, deterministic compilation: the model emits a typed design, never executable diagram code."""

import re

from app.models import Architecture, DiagramType

STYLE = """skinparam backgroundColor transparent
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam defaultFontSize 15
skinparam roundcorner 10
skinparam ArrowColor #6A8075
skinparam ArrowFontColor #46554E
skinparam LineThickness 1
skinparam classAttributeIconSize 0
skinparam packageStyle rectangle
skinparam componentStyle uml2
skinparam default {
  BackgroundColor #FFFFFF
  BorderColor #789185
  FontColor #263E33
}
skinparam databaseBackgroundColor #EAF0E7
skinparam queueBackgroundColor #F8F0DE
skinparam actorStyle awesome
"""


def text(value: str) -> str:
    # Newlines, quotes, Creole, preprocessor, and link delimiters never reach PlantUML grammar.
    value = value.replace(";", ",")
    value = re.sub(r"([A-Z]\w*)<([^<>]+)>", r"\1 of \2", value)
    for symbol, phrase in (
        (">=", " at least "),
        ("<=", " at most "),
        ("!=", " differs from "),
        (">", " above "),
        ("<", " below "),
    ):
        value = value.replace(symbol, phrase)
    value = re.sub(r"[^\w .,:/()+?=\-]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()[:240] or "Unnamed"


def quoted(value: str) -> str:
    return f'"{text(value)}"'


def compile_diagram(a: Architecture, kind: DiagramType) -> str:
    # Prefix private grammar aliases so legitimate IDs such as "class" never become keywords.
    a = a.model_copy(deep=True)
    components = {c.id: f"c_{c.id}" for c in a.components}
    entities = {e.id: f"e_{e.id}" for e in a.entities}
    for c in a.components:
        c.id = components[c.id]
    for e in a.entities:
        e.id = entities[e.id]
    for link in [*a.connections, *a.interactions]:
        link.source, link.target = components[link.source], components[link.target]
    for relation in a.relations:
        relation.source, relation.target = entities[relation.source], entities[relation.target]
    for step in a.steps:
        step.owner = components[step.owner]
    for node in a.nodes:
        node.components = [components[c] for c in node.components]
    for timeline in a.timelines:
        timeline.component = components[timeline.component]
    lines = ["@startuml", STYLE, f"title {text(a.title)} / {kind.value.replace('_', ' ').title()}"]
    names = {c.id: c.name for c in a.components}
    if kind == DiagramType.COMPONENT:
        lines.append("top to bottom direction")
        for package in dict.fromkeys(c.package for c in a.components):
            lines.append(f"package {quoted(package)} {{")
            for c in a.components:
                if c.package != package:
                    continue
                shape = {
                    "service": "component",
                    "database": "database",
                    "external": "cloud",
                    "queue": "queue",
                    "ui": "component",
                }[c.kind]
                lines.append(f"  {shape} {quoted(c.name)} as {c.id}")
            lines.append("}")
        for c in a.connections:
            # Forced lateral ranks can make cyclic retry graphs prohibitively slow to lay out.
            arrow = "..>" if c.kind == "dependency" else "-->"
            label = ("async: " if c.kind == "async" else "") + c.label
            lines.append(f"{c.source} {arrow} {c.target} : {text(label)}")
    elif kind == DiagramType.SEQUENCE:
        lines.extend(["autonumber", "hide footbox", "skinparam sequenceMessageAlign center"])
        for c in a.components:
            shape = {
                "database": "database",
                "queue": "queue",
                "external": "participant",
                "service": "participant",
                "ui": "boundary",
            }[c.kind]
            lines.append(f"{shape} {quoted(c.name)} as {c.id}")
        for i in a.interactions:
            if i.fragment != "none":
                lines.append(f"{i.fragment} {text(i.condition or '')}")
            arrow = {"call": "->", "return": "-->", "async": "->>"}[i.kind]
            lines.append(f"{i.source} {arrow} {i.target} : {text(i.message)}")
            if i.fragment != "none":
                lines.append("end")
    elif kind in [DiagramType.CLASS, DiagramType.OBJECT]:
        for e in a.entities:
            declaration = "class" if kind == DiagramType.CLASS else "object"
            label = e.name if kind == DiagramType.CLASS else f"sample_{e.id} : {e.name}"
            lines.append(f"{declaration} {quoted(label)} as {e.id} {{")
            if kind == DiagramType.CLASS:
                lines.extend(f"  +{text(m.name)} : {text(m.type)}" for m in e.attributes)
                lines.extend(f"  +{text(op)}" for op in e.operations)
            else:
                lines.extend(f"  {text(m.name)} = {text(m.type)}" for m in e.example_values)
            lines.append("}")
        for r in a.relations:
            arrow = {"association": "--", "composition": "*--", "aggregation": "o--", "inheritance": "--|>"}[
                r.kind
            ]
            if kind == DiagramType.OBJECT:
                arrow = "--"
                lines.append(f"{r.source} {arrow} {r.target} : {text(r.label)}")
            else:
                lines.append(
                    f'{r.source} "{r.source_multiplicity}" {arrow} "{r.target_multiplicity}" {r.target} : {text(r.label)}'
                )
        if kind == DiagramType.OBJECT:
            lines.append("caption Illustrative instance snapshot; values are examples")
    elif kind == DiagramType.COMPOSITE_STRUCTURE:
        # PlantUML composite view built with UML2 component parts and explicit boundary ports.
        selected = [c for c in a.components if c.parts]
        if not selected:
            lines.extend(
                [f"component {quoted(a.title)} as whole {{"]
                + [f"component {quoted(c.name)} as part_{c.id}" for c in a.components]
                + ["}"]
            )
            for c in a.connections:
                lines.append(f"part_{c.source} --> part_{c.target} : {text(c.label)}")
        else:
            for c in selected:
                lines.append(f"component {quoted(c.name)} as whole_{c.id} {{")
                for index, p in enumerate(c.parts):
                    lines.append(f"component {quoted(p.name + ' : ' + p.type)} as part_{c.id}_{index}")
                for index, port in enumerate(c.ports):
                    shape = "portin" if port.direction == "in" else "portout"
                    lines.append(f"{shape} {quoted(port.name)} as port_{c.id}_{index}")
                lines.append("}")
                for index, port in enumerate(c.ports):
                    part_index = next(j for j, p in enumerate(c.parts) if p.name == port.part)
                    if port.direction == "in":
                        lines.append(f"port_{c.id}_{index} --> part_{c.id}_{part_index}")
                    else:
                        lines.append(f"part_{c.id}_{part_index} --> port_{c.id}_{index}")
            lines.append("caption Parts, boundary ports, and delegation connectors")
    elif kind == DiagramType.DEPLOYMENT:
        aliases: dict[str, str] = {}
        for i, n in enumerate(a.nodes):
            shape = {"device": "node", "container": "node", "cloud": "cloud", "database": "database"}[n.kind]
            lines.append(f"{shape} {quoted(n.name)} as node_{i} {{")
            for cid in n.components:
                alias = f"artifact_{i}_{cid}"
                aliases.setdefault(cid, alias)
                lines.append(f"artifact {quoted(names[cid])} as {alias}")
            lines.append("}")
        for c in a.connections:
            if c.source in aliases and c.target in aliases:
                lines.append(f"{aliases[c.source]} --> {aliases[c.target]} : {text(c.label)}")
        lines.append("caption Proposed runtime topology")
    elif kind == DiagramType.PACKAGE:
        packages = list(dict.fromkeys(c.package for c in a.components))
        mapping = {p: f"pkg_{i}" for i, p in enumerate(packages)}
        cp = {c.id: mapping[c.package] for c in a.components}
        for p in packages:
            lines.append(f"package {quoted(p)} as {mapping[p]} {{")
            lines.extend(f"component {quoted(c.name)} as {c.id}" for c in a.components if c.package == p)
            lines.append("}")
        edges = dict.fromkeys(
            (cp[c.source], cp[c.target]) for c in a.connections if cp[c.source] != cp[c.target]
        )
        lines.extend(f"{s} ..> {t} : depends on" for s, t in edges)
    elif kind == DiagramType.PROFILE:
        lines.append(f"package {quoted(a.title + ' profile')} <<profile>> {{")
        for i, s in enumerate(a.stereotypes):
            lines.append(f"class {quoted(s.name)} as stereo_{i} <<stereotype>> {{")
            lines.extend(f"  {text(t.name)} : {text(t.type)}" for t in s.tags)
            lines.append("}")
            lines.append(f"note right of stereo_{i} : Constraint: {text(s.constraint)}")
        lines.append("}")
        for base in dict.fromkeys(s.base for s in a.stereotypes):
            lines.append(f"class {base} <<metaclass>>")
        for i, s in enumerate(a.stereotypes):
            lines.append(f"stereo_{i} --|> {s.base} : extends")
    elif kind == DiagramType.USE_CASE:
        lines.append("left to right direction")
        goals = list(dict.fromkeys(g for actor in a.actors for g in actor.goals))
        for i, actor in enumerate(a.actors):
            lines.append(f"actor {quoted(actor.name)} as actor_{i}")
        lines.append(f"rectangle {quoted(a.title)} {{")
        lines.extend(f"usecase {quoted(g)} as goal_{i}" for i, g in enumerate(goals))
        lines.append("}")
        for i, actor in enumerate(a.actors):
            lines.extend(f"actor_{i} --> goal_{goals.index(g)}" for g in actor.goals)
    elif kind == DiagramType.ACTIVITY:
        lines.append("start")
        for s in a.steps:
            lines.extend([f"partition {quoted(names[s.owner])} {{", f":{text(s.action)};"])
            if s.guard:
                lines.extend(
                    [
                        f"if ({text(s.guard)}) then (yes)",
                        ":Continue;",
                        "else (no)",
                        f":{text(s.alternative or '')};",
                        "stop",
                        "endif",
                    ]
                )
            if s.parallel_actions:
                for index, p in enumerate(s.parallel_actions):
                    lines.extend(["fork" if index == 0 else "fork again", f":{text(p)};"])
                lines.append("end fork")
            lines.append("}")
        lines.append("stop")
    elif kind == DiagramType.STATE_MACHINE:
        for i, s in enumerate(a.states):
            lines.append(f"state {quoted(s)} as state_{i}")
        lines.append("[*] --> state_0")
        for t in a.transitions:
            label = text(t.event) + (f" [{text(t.guard)}]" if t.guard else "")
            lines.append(f"state_{a.states.index(t.source)} --> state_{a.states.index(t.target)} : {label}")
        lines.append(f"state_{len(a.states) - 1} --> [*]")
    elif kind == DiagramType.COMMUNICATION:
        lines.append("left to right direction")
        for c in a.components:
            lines.append(f"object {quoted(c.name)} as {c.id}")
        for index, i in enumerate(a.interactions, 1):
            label = f"{index}: {text(i.message)}"
            if i.condition:
                label += f" [{text(i.condition)}]"
            lines.append(f"{i.source} --> {i.target} : {label}")
        lines.append("caption Communication view: linked participants with numbered messages")
    elif kind == DiagramType.INTERACTION_OVERVIEW:
        lines.append("start")
        for s in a.steps:
            # UML interaction uses rendered as stereotyped activity references.
            lines.extend([f":ref {text(names[s.owner])}\n{text(s.action)}; <<procedure>>"])
            if s.guard:
                lines.extend(
                    [
                        f"if ({text(s.guard)}) then (yes)",
                        ":Continue;",
                        "else (no)",
                        f":ref Manual review\n{text(s.alternative or '')}; <<procedure>>",
                        "stop",
                        "endif",
                    ]
                )
        lines.extend(
            ["stop", "caption Interaction overview using activity notation and interaction references"]
        )
    elif kind == DiagramType.TIMING:
        for index, t in enumerate(a.timelines):
            lines.append(f"robust {quoted(names[t.component])} as timeline_{index}")
        timestamps = sorted({x.time_ms for t in a.timelines for x in t.ticks})
        for time in timestamps:
            lines.append(f"@{time}")
            for index, t in enumerate(a.timelines):
                for tick in t.ticks:
                    if tick.time_ms == time:
                        lines.append(f"timeline_{index} is {quoted(tick.state)}")
        lines.append("caption Time in milliseconds; illustrative values, not measured latency")
    else:
        raise ValueError(f"Unsupported diagram: {kind}")
    lines.append("@enduml")
    return "\n".join(lines)
