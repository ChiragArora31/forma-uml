from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiagramType(StrEnum):
    SEQUENCE = "sequence"
    COMPONENT = "component"
    CLASS = "class"
    OBJECT = "object"
    COMPOSITE_STRUCTURE = "composite_structure"
    DEPLOYMENT = "deployment"
    PACKAGE = "package"
    PROFILE = "profile"
    USE_CASE = "use_case"
    ACTIVITY = "activity"
    STATE_MACHINE = "state_machine"
    COMMUNICATION = "communication"
    INTERACTION_OVERVIEW = "interaction_overview"
    TIMING = "timing"


CATALOG = [
    ("sequence", "Sequence", "interaction", "Time-ordered calls and responses"),
    ("component", "Component", "structure", "Services, stores, and their boundaries"),
    ("class", "Class", "structure", "Domain models, attributes, and relationships"),
    ("object", "Object", "structure", "An illustrative snapshot of domain instances"),
    ("composite_structure", "Composite structure", "structure", "Internal parts, ports, and connectors"),
    ("deployment", "Deployment", "structure", "Runtime nodes and deployed artifacts"),
    ("package", "Package", "structure", "Layers, namespaces, and dependencies"),
    ("profile", "Profile", "structure", "Stereotypes, tagged values, and constraints"),
    ("use_case", "Use case", "behavior", "Actors, goals, and system scope"),
    ("activity", "Activity", "behavior", "Workflow, decisions, and parallel actions"),
    ("state_machine", "State machine", "behavior", "States, guarded transitions, and lifecycle"),
    ("communication", "Communication", "interaction", "Numbered messages between linked participants"),
    (
        "interaction_overview",
        "Interaction overview",
        "interaction",
        "Control flow linking named interactions",
    ),
    ("timing", "Timing", "interaction", "Illustrative state changes over time"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Member(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    type: str = Field(min_length=1, max_length=60)


class Part(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    type: str = Field(min_length=1, max_length=60)


class Port(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    direction: Literal["in", "out"]
    part: str = Field(
        min_length=1,
        max_length=60,
        description="Exact name of a part declared in this component's parts, not a type or ID.",
    )


class Component(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str = Field(min_length=1, max_length=70)
    responsibility: str = Field(min_length=1, max_length=240)
    kind: Literal["service", "database", "external", "queue", "ui"]
    package: str = Field(min_length=1, max_length=60)
    parts: list[Part] = Field(max_length=8)
    ports: list[Port] = Field(max_length=8)

    @model_validator(mode="after")
    def ports_reference_parts(self):
        names = [p.name for p in self.parts]
        if len(names) != len(set(names)):
            raise ValueError("Part names must be unique")
        unknown = [p.part for p in self.ports if p.part not in names]
        if unknown:
            raise ValueError(f"Ports reference unknown parts {unknown}. Available parts: {names}")
        return self


class Connection(StrictModel):
    source: str = Field(description="ID declared in components. Never use an actor name or entity ID.")
    target: str = Field(description="ID declared in components. Never use an actor name or entity ID.")
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["sync", "async", "dependency"]


class Entity(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    attributes: list[Member] = Field(max_length=12)
    operations: list[str] = Field(max_length=8)
    example_values: list[Member] = Field(max_length=12)


class Relation(StrictModel):
    source: str = Field(description="ID declared in entities. Service/component IDs are not domain entities.")
    target: str = Field(description="ID declared in entities. Service/component IDs are not domain entities.")
    kind: Literal["association", "composition", "aggregation", "inheritance"]
    source_multiplicity: Literal["1", "0..1", "*", "1..*", "0..*"]
    target_multiplicity: Literal["1", "0..1", "*", "1..*", "0..*"]
    label: str = Field(min_length=1, max_length=80)


class Actor(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    goals: list[str] = Field(min_length=1, max_length=6)


class Step(StrictModel):
    action: str = Field(min_length=1, max_length=140)
    owner: str = Field(
        description="ID declared in components. Human actions belong to the participating workspace/UI component."
    )
    guard: str | None = Field(
        max_length=100, description="A decision condition; when present, alternative must also be nonempty."
    )
    alternative: str | None = Field(
        max_length=140, description="What happens when the guard is false. Empty only when guard is empty."
    )
    parallel_actions: list[str] = Field(max_length=4)


class Interaction(StrictModel):
    source: str = Field(
        description="ID declared in components. Represent external participants as declared components."
    )
    target: str = Field(
        description="ID declared in components. Represent external participants as declared components."
    )
    message: str = Field(min_length=1, max_length=100)
    kind: Literal["call", "return", "async"]
    fragment: Literal["none", "loop", "alt"]
    condition: str | None = Field(
        max_length=100,
        description="Required nonempty condition when fragment is loop or alt. Empty is allowed only for none.",
    )


class Transition(StrictModel):
    source: str = Field(description="Exact state name declared in states.")
    target: str = Field(description="Exact state name declared in states.")
    event: str = Field(min_length=1, max_length=100)
    guard: str | None = Field(max_length=100)


class Node(StrictModel):
    name: str = Field(min_length=1, max_length=70)
    kind: Literal["device", "container", "cloud", "database"]
    components: list[str] = Field(min_length=1, max_length=12, description="Only IDs declared in components.")


class Stereotype(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    base: Literal["Component", "Class", "Node"]
    tags: list[Member] = Field(max_length=5)
    constraint: str = Field(min_length=1, max_length=160)


class Tick(StrictModel):
    time_ms: int = Field(ge=0, le=1_000_000)
    state: str = Field(min_length=1, max_length=50)


class Timeline(StrictModel):
    component: str = Field(description="ID declared in components, never an actor or entity ID.")
    ticks: list[Tick] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def ticks_are_ordered(self):
        times = [t.time_ms for t in self.ticks]
        if times != sorted(set(times)):
            raise ValueError("Timeline ticks must have strictly increasing timestamps")
        return self


class Architecture(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    requirements: list[str] = Field(min_length=1, max_length=15)
    assumptions: list[str] = Field(min_length=1, max_length=12)
    components: list[Component] = Field(min_length=2, max_length=16)
    connections: list[Connection] = Field(min_length=1, max_length=30)
    entities: list[Entity] = Field(min_length=1, max_length=10)
    relations: list[Relation] = Field(max_length=20)
    actors: list[Actor] = Field(min_length=1, max_length=6)
    steps: list[Step] = Field(min_length=1, max_length=12)
    interactions: list[Interaction] = Field(min_length=1, max_length=24)
    states: list[str] = Field(min_length=2, max_length=12)
    transitions: list[Transition] = Field(min_length=1, max_length=20)
    nodes: list[Node] = Field(min_length=1, max_length=8)
    stereotypes: list[Stereotype] = Field(min_length=1, max_length=5)
    timelines: list[Timeline] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def references_are_consistent(self):
        cids = {c.id for c in self.components}
        eids = {e.id for e in self.entities}
        if len(cids) != len(self.components) or len(eids) != len(self.entities):
            raise ValueError("Component and entity IDs must be unique")
        if len(set(self.states)) != len(self.states):
            raise ValueError("State names must be unique")
        unknown = {
            ref for x in [*self.connections, *self.interactions] for ref in (x.source, x.target)
        } - cids
        issues = []
        if unknown:
            issues.append(
                f"Connection or interaction references unknown component IDs {sorted(unknown)}. Available: {sorted(cids)}"
            )
        for r in self.relations:
            if r.source not in eids or r.target not in eids:
                issues.append(
                    f"Relation references an unknown entity ({r.source}, {r.target}). Available: {sorted(eids)}"
                )
        unknown_owners = sorted({s.owner for s in self.steps} - cids)
        if unknown_owners:
            issues.append(
                f"Workflow step references an unknown owner {unknown_owners}. Available: {sorted(cids)}"
            )
        if any(c not in cids for n in self.nodes for c in n.components):
            issues.append("Deployment references an unknown component")
        if any(t.component not in cids for t in self.timelines):
            issues.append("Timeline references an unknown component")
        for t in self.transitions:
            if t.source not in self.states or t.target not in self.states:
                issues.append("Transition references an unknown state")
        for i in self.interactions:
            if i.fragment != "none" and not i.condition:
                issues.append("An interaction fragment requires a condition")
        for s in self.steps:
            if bool(s.guard) != bool(s.alternative):
                issues.append("A guarded workflow step needs an alternative")
        if issues:
            raise ValueError("; ".join(issues))
        return self


class GenerateRequest(StrictModel):
    prompt: str = Field(min_length=10, max_length=12000)
    diagram_types: list[DiagramType] = Field(
        default_factory=lambda: [DiagramType.SEQUENCE, DiagramType.COMPONENT], min_length=1, max_length=14
    )
    conversation_id: UUID | None = None
    base_revision: int | None = Field(default=None, ge=1)
    request_id: UUID = Field(default_factory=uuid4)
    mode: Literal["sample", "live"] | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v):
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Describe your design in at least 10 characters")
        return v

    @field_validator("diagram_types", mode="before")
    @classmethod
    def normalize_types(cls, v):
        aliases = {"sequential": "sequence", "state": "state_machine", "usecase": "use_case"}
        return list(dict.fromkeys(aliases.get(x, x) for x in v)) if isinstance(v, list) else v

    @model_validator(mode="after")
    def revision_for_update(self):
        if self.conversation_id and self.base_revision is None:
            raise ValueError("base_revision is required when updating a conversation")
        if not self.conversation_id and self.base_revision is not None:
            raise ValueError("base_revision requires conversation_id")
        return self


class FeedbackRequest(StrictModel):
    revision_id: UUID
    rating: Literal[1, 2, 3, 4, 5]
    comment: str = Field(default="", max_length=4000)
    diagram_type: DiagramType | None = None
    request_id: UUID = Field(default_factory=uuid4)


class SourceRequest(StrictModel):
    source: str = Field(min_length=10, max_length=30000)


class ConversationUpdateRequest(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None

    @model_validator(mode="after")
    def meaningful_update(self):
        if self.title is None and self.archived is None:
            raise ValueError("Specify a title or archive state")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("A design name cannot be blank")
        return self
