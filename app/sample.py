"""Explicit, deterministic case study. Sample mode never pretends to call a model."""

import copy

from app.models import Architecture

SEBI_PROMPT = """I am working on a compliance monitoring solution which will pull in the latest circulars from SEBI and parse them. Once it is parsed into a table of clauses, extract:
1. The new compliance requirements proposed by the regulator
2. Gap analysis with my existing compliance setup
3. The impact of these new compliance requirements on my organization at an IT and operational level"""
ASYNC_PROMPT = (
    "Decouple circular ingestion from analysis using a durable queue, with retries and a dead-letter queue."
)
APPROVAL_PROMPT = "Add a compliance officer approval step before publishing the impact report."


def component(id, name, responsibility, kind="service", package="Analysis", parts=None, ports=None):
    return dict(
        id=id,
        name=name,
        responsibility=responsibility,
        kind=kind,
        package=package,
        parts=parts or [],
        ports=ports or [],
    )


def entity(id, name, attributes, operations, values):
    return dict(
        id=id,
        name=name,
        attributes=[dict(name=k, type=v) for k, v in attributes],
        operations=operations,
        example_values=[dict(name=k, type=v) for k, v in values],
    )


BASE = {
    "title": "SEBI compliance monitor",
    "summary": "A provenance-first pipeline turns regulator circulars into clause-level requirements, compares them with the organization's controls, and produces an IT and operational impact report. A compliance officer reviews uncertain interpretations; the system supports analysis rather than making legal determinations.",
    "requirements": [
        "Ingest the latest SEBI circulars with source URL, date, and document hash.",
        "Parse each circular into a clause table while retaining source references.",
        "Extract proposed compliance requirements with supporting evidence.",
        "Compare requirements against the organization's current controls.",
        "Assess IT changes, operational ownership, and implementation impact.",
    ],
    "assumptions": [
        "This is a proposed software architecture, not an implementation of SEBI ingestion or a statement of legal requirements.",
        "The organization supplies a versioned inventory of existing controls; absence of evidence is flagged for review rather than treated as a confirmed gap.",
        "Circulars may be PDFs, including scanned documents; OCR results require confidence checks.",
        "Uncertain clauses are routed to a compliance officer for interpretation.",
        "Timing values and object instances are illustrative, not measured SLA commitments.",
        "Deployment nodes and domain stereotypes are proposed design decisions.",
    ],
    "components": [
        component(
            "sebi",
            "SEBI circular feed",
            "Official source documents and publication metadata",
            "external",
            "Sources",
        ),
        component(
            "ingest",
            "Circular ingestion",
            "Deduplicate documents; retain hash, date, and original source",
            package="Ingestion",
        ),
        component(
            "parse",
            "Clause parser",
            "Extract/OCR text into a provenance-linked clause table",
            package="Ingestion",
            parts=[
                dict(name="extractor", type="PDF extractor"),
                dict(name="ocr", type="OCR adapter"),
                dict(name="normalizer", type="Clause normalizer"),
            ],
            ports=[
                dict(name="document", direction="in", part="extractor"),
                dict(name="clauses", direction="out", part="normalizer"),
            ],
        ),
        component(
            "requirements", "Requirement extraction", "Identify obligations with evidence and confidence"
        ),
        component(
            "controls",
            "Control inventory",
            "Organization's versioned compliance setup",
            "database",
            "Evidence",
        ),
        component("gap", "Gap analysis", "Compare requirements to controls; flag missing evidence"),
        component(
            "impact", "Impact assessment", "Assess IT change, operational owner, and implementation effort"
        ),
        component(
            "evidence",
            "Evidence store",
            "Persist circulars, clauses, requirements, and reports",
            "database",
            "Evidence",
        ),
        component(
            "portal", "Compliance workspace", "Review evidence, gaps, and impact reports", "ui", "Experience"
        ),
    ],
    "connections": [
        dict(source="sebi", target="ingest", label="Published circulars", kind="sync"),
        dict(source="ingest", target="parse", label="Source document + provenance", kind="sync"),
        dict(source="parse", target="requirements", label="Clause table", kind="sync"),
        dict(source="requirements", target="gap", label="Evidence-linked requirements", kind="sync"),
        dict(source="controls", target="gap", label="Current control baseline", kind="sync"),
        dict(source="gap", target="impact", label="Gaps + affected processes", kind="sync"),
        dict(source="impact", target="evidence", label="Versioned impact report", kind="sync"),
        dict(source="portal", target="evidence", label="Review analysis and evidence", kind="sync"),
    ],
    "entities": [
        entity(
            "circular",
            "Circular",
            [("source_url", "URL"), ("published_at", "Date"), ("sha256", "String")],
            ["deduplicate()", "verifySource()"],
            [("source_url", "illustrative circular"), ("sha256", "sample hash")],
        ),
        entity(
            "clause",
            "Clause",
            [("clause_id", "String"), ("text", "String"), ("page", "Integer")],
            ["extractEvidence()"],
            [("clause_id", "clause-01"), ("page", "3")],
        ),
        entity(
            "requirement",
            "Requirement",
            [("obligation", "String"), ("confidence", "Float")],
            ["reviewInterpretation()"],
            [("obligation", "illustrative obligation"), ("confidence", "0.85")],
        ),
        entity(
            "control",
            "Control",
            [("owner", "String"), ("evidence_ref", "String"), ("version", "Integer")],
            ["matchRequirement()"],
            [("owner", "Compliance team"), ("version", "2")],
        ),
        entity(
            "gap_report",
            "GapReport",
            [("status", "GapStatus"), ("missing_evidence", "Boolean")],
            ["assessCoverage()"],
            [("status", "Needs review"), ("missing_evidence", "true")],
        ),
        entity(
            "report",
            "ImpactReport",
            [("it_changes", "String"), ("operational_owner", "String")],
            ["publish()"],
            [("it_changes", "illustrative change"), ("operational_owner", "Operations")],
        ),
    ],
    "relations": [
        dict(
            source="circular",
            target="clause",
            kind="composition",
            source_multiplicity="1",
            target_multiplicity="1..*",
            label="contains",
        ),
        dict(
            source="clause",
            target="requirement",
            kind="association",
            source_multiplicity="1",
            target_multiplicity="0..*",
            label="supports",
        ),
        dict(
            source="requirement",
            target="control",
            kind="association",
            source_multiplicity="*",
            target_multiplicity="*",
            label="compared against",
        ),
        dict(
            source="requirement",
            target="gap_report",
            kind="association",
            source_multiplicity="1",
            target_multiplicity="0..*",
            label="assessed by",
        ),
        dict(
            source="gap_report",
            target="report",
            kind="association",
            source_multiplicity="1..*",
            target_multiplicity="1",
            label="informs",
        ),
    ],
    "actors": [
        dict(
            name="Compliance officer",
            goals=["Review new requirements", "Inspect control gaps", "Review impact report"],
        ),
        dict(name="IT owner", goals=["Plan IT changes"]),
        dict(name="Operations owner", goals=["Assign operational actions"]),
    ],
    "steps": [
        dict(
            action="Fetch and deduplicate latest circulars",
            owner="ingest",
            guard=None,
            alternative=None,
            parallel_actions=[],
        ),
        dict(
            action="Parse document into evidence-linked clauses",
            owner="parse",
            guard="Extraction confidence sufficient?",
            alternative="Route low-confidence clauses for manual review",
            parallel_actions=[],
        ),
        dict(
            action="Extract proposed requirements with citations",
            owner="requirements",
            guard=None,
            alternative=None,
            parallel_actions=[],
        ),
        dict(
            action="Compare requirements with current controls",
            owner="gap",
            guard=None,
            alternative=None,
            parallel_actions=[],
        ),
        dict(
            action="Assess organizational impact",
            owner="impact",
            guard=None,
            alternative=None,
            parallel_actions=[
                "Assess IT systems and data changes",
                "Assess operational processes and owners",
            ],
        ),
        dict(
            action="Persist and display impact report with evidence",
            owner="portal",
            guard=None,
            alternative=None,
            parallel_actions=[],
        ),
    ],
    "interactions": [
        dict(
            source="portal",
            target="ingest",
            message="Refresh circulars",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="ingest",
            target="sebi",
            message="Fetch publication metadata + document",
            kind="call",
            fragment="loop",
            condition="Each unseen circular",
        ),
        dict(
            source="sebi",
            target="ingest",
            message="Circular + source reference",
            kind="return",
            fragment="none",
            condition=None,
        ),
        dict(
            source="ingest",
            target="parse",
            message="Parse to clause table",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="parse",
            target="requirements",
            message="Extract requirements + citations",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="requirements",
            target="gap",
            message="Compare requirements",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="gap",
            target="controls",
            message="Read versioned control baseline",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="controls",
            target="gap",
            message="Controls + evidence",
            kind="return",
            fragment="none",
            condition=None,
        ),
        dict(
            source="gap",
            target="impact",
            message="Assess IT + operational impact",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="impact",
            target="evidence",
            message="Store versioned report",
            kind="call",
            fragment="none",
            condition=None,
        ),
        dict(
            source="evidence",
            target="portal",
            message="Report + source citations",
            kind="return",
            fragment="none",
            condition=None,
        ),
    ],
    "states": ["Discovered", "Parsed", "Analyzed", "Needs review", "Published"],
    "transitions": [
        dict(
            source="Discovered", target="Parsed", event="Extraction completed", guard="Confidence sufficient"
        ),
        dict(source="Discovered", target="Needs review", event="Extraction uncertain", guard=None),
        dict(source="Needs review", target="Parsed", event="Manual correction", guard=None),
        dict(source="Parsed", target="Analyzed", event="Gap and impact analysis completed", guard=None),
        dict(source="Analyzed", target="Published", event="Report available", guard=None),
    ],
    "nodes": [
        dict(name="Regulator website", kind="cloud", components=["sebi"]),
        dict(
            name="Application container",
            kind="container",
            components=["ingest", "parse", "requirements", "gap", "impact"],
        ),
        dict(name="Organization data", kind="database", components=["controls", "evidence"]),
        dict(name="Officer workstation", kind="device", components=["portal"]),
    ],
    "stereotypes": [
        dict(
            name="EvidenceLinked",
            base="Class",
            tags=[dict(name="source_ref", type="URL"), dict(name="reviewed", type="Boolean")],
            constraint="Each extracted obligation retains a source clause reference",
        ),
        dict(
            name="Auditable",
            base="Component",
            tags=[dict(name="retention", type="Duration")],
            constraint="Persist an immutable record of each analysis version",
        ),
    ],
    "timelines": [
        dict(
            component="ingest",
            ticks=[
                dict(time_ms=0, state="Idle"),
                dict(time_ms=100, state="Fetching"),
                dict(time_ms=400, state="Stored"),
            ],
        ),
        dict(
            component="impact",
            ticks=[
                dict(time_ms=0, state="Waiting"),
                dict(time_ms=500, state="Assessing"),
                dict(time_ms=900, state="Complete"),
            ],
        ),
    ],
}


class SampleUnavailable(ValueError):
    pass


def sample_architecture(prompt: str, previous: Architecture | None = None) -> Architecture:
    if previous is None:
        # The complete supplied brief is accepted; arbitrary prompts require a live provider.
        p = prompt.lower()
        if not all(w in p for w in ["sebi", "clause", "gap", "impact"]):
            raise SampleUnavailable(
                "Sample mode supports the SEBI case study. Switch to live mode for your own design."
            )
        return Architecture.model_validate(copy.deepcopy(BASE))
    a = previous.model_dump()
    p = prompt.strip().lower()
    if p == ASYNC_PROMPT.lower():
        if not any(c["id"] == "queue" for c in a["components"]):
            a["components"].extend(
                [
                    component(
                        "queue",
                        "Analysis queue",
                        "Durable circular processing jobs with retries",
                        "queue",
                        "Ingestion",
                    ),
                    component(
                        "dlq",
                        "Dead-letter queue",
                        "Failed jobs retained for operator inspection and replay",
                        "queue",
                        "Ingestion",
                    ),
                ]
            )
            a["connections"] = [
                c for c in a["connections"] if not (c["source"] == "ingest" and c["target"] == "parse")
            ]
            a["connections"].extend(
                [
                    dict(
                        source="ingest", target="queue", label="Enqueue idempotent document job", kind="async"
                    ),
                    dict(source="queue", target="parse", label="Consume with bounded retries", kind="async"),
                    dict(source="parse", target="dlq", label="Exhausted retries", kind="async"),
                ]
            )
            index = next(
                i
                for i, x in enumerate(a["interactions"])
                if x["source"] == "ingest" and x["target"] == "parse"
            )
            a["interactions"][index : index + 1] = [
                dict(
                    source="ingest",
                    target="queue",
                    message="Enqueue circular job",
                    kind="async",
                    fragment="none",
                    condition=None,
                ),
                dict(
                    source="queue",
                    target="parse",
                    message="Deliver job; bounded retries",
                    kind="async",
                    fragment="loop",
                    condition="Retry policy permits",
                ),
                dict(
                    source="parse",
                    target="dlq",
                    message="Retain failed job for replay",
                    kind="async",
                    fragment="alt",
                    condition="Retries exhausted",
                ),
            ]
            a["steps"].insert(
                1,
                dict(
                    action="Enqueue idempotent processing job",
                    owner="queue",
                    guard=None,
                    alternative=None,
                    parallel_actions=[],
                ),
            )
            a["nodes"][1]["components"].extend(["queue", "dlq"])
            a["requirements"].append(
                "Decouple ingestion from analysis with durable jobs, bounded retries, and a dead-letter queue."
            )
            a["assumptions"].append(
                "Workers use the circular hash as an idempotency key; operators inspect and replay failed jobs."
            )
    elif p == APPROVAL_PROMPT.lower():
        if not any(c["id"] == "approval" for c in a["components"]):
            a["components"].append(
                component(
                    "approval",
                    "Officer approval",
                    "Require explicit officer sign-off before publishing",
                    package="Experience",
                )
            )
            a["connections"] = [
                c for c in a["connections"] if not (c["source"] == "impact" and c["target"] == "evidence")
            ]
            a["connections"].extend(
                [
                    dict(source="impact", target="approval", label="Draft impact report", kind="sync"),
                    dict(
                        source="approval",
                        target="evidence",
                        label="Approved report + reviewer identity",
                        kind="sync",
                    ),
                    dict(source="portal", target="approval", label="Officer sign-off", kind="sync"),
                ]
            )
            index = next(
                i
                for i, x in enumerate(a["interactions"])
                if x["source"] == "impact" and x["target"] == "evidence"
            )
            a["interactions"][index : index + 1] = [
                dict(
                    source="impact",
                    target="approval",
                    message="Submit draft report",
                    kind="call",
                    fragment="none",
                    condition=None,
                ),
                dict(
                    source="portal",
                    target="approval",
                    message="Record officer decision",
                    kind="call",
                    fragment="none",
                    condition=None,
                ),
                dict(
                    source="approval",
                    target="evidence",
                    message="Publish approved report",
                    kind="call",
                    fragment="alt",
                    condition="Officer approved",
                ),
            ]
            a["steps"].insert(
                -1,
                dict(
                    action="Compliance officer reviews draft",
                    owner="approval",
                    guard="Officer approved?",
                    alternative="Return for revision; do not publish",
                    parallel_actions=[],
                ),
            )
            a["states"].insert(-1, "Awaiting approval")
            a["transitions"] = [
                t for t in a["transitions"] if not (t["source"] == "Analyzed" and t["target"] == "Published")
            ]
            a["transitions"].extend(
                [
                    dict(source="Analyzed", target="Awaiting approval", event="Draft submitted", guard=None),
                    dict(
                        source="Awaiting approval",
                        target="Published",
                        event="Officer approves",
                        guard="Reviewer identity recorded",
                    ),
                    dict(
                        source="Awaiting approval", target="Needs review", event="Officer rejects", guard=None
                    ),
                ]
            )
            a["nodes"][1]["components"].append("approval")
            a["requirements"].append(
                "A compliance officer must approve the impact report before publication."
            )
            a["actors"][0]["goals"].append("Approve publication")
    else:
        raise SampleUnavailable(
            "Sample revisions support the two suggested changes only. Live mode accepts arbitrary updates."
        )
    return Architecture.model_validate(a)
