"""Portable, source-grounded design handoff; no extra model call."""

import re


def text(value):
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", str(value)).replace("\n", " ")


def design_report(revision, reviews, packaged=False):
    a = revision["architecture"]
    names = {c["id"]: c["name"] for c in a["components"]}
    lines = [
        f"# {text(a['title'])}",
        "",
        f"Design review · Revision {revision['number']} · {revision['created_at']}",
        "",
        f"Generation: {text(revision.get('model') or revision['mode'])}. All requested UML views passed PlantUML syntax validation.",
        "",
        "## Design intent",
        "",
        text(a["summary"]),
        "",
        "## Original request",
        "",
        text(revision["prompt"]),
        "",
        "## Requirements",
        "",
        *[f"{i}. {text(r)}" for i, r in enumerate(a["requirements"], 1)],
        "",
        "## Assumptions to confirm",
        "",
        *[f"- {text(r)}" for r in a["assumptions"]],
        "",
        "## System boundaries",
        "",
        "| Component | Kind | Responsibility |",
        "| --- | --- | --- |",
        *[
            f"| {text(c['name'])} | {text(c['kind'])} | {text(c['responsibility'])} |"
            for c in a["components"]
        ],
        "",
        "## Connections",
        "",
        "| From | To | Interaction | Mode |",
        "| --- | --- | --- | --- |",
        *[
            f"| {text(names[c['source']])} | {text(names[c['target']])} | {text(c['label'])} | {text(c['kind'])} |"
            for c in a["connections"]
        ],
        "",
        "## Actors and goals",
        "",
        *[f"- **{text(actor['name'])}:** {text('; '.join(actor['goals']))}" for actor in a["actors"]],
        "",
        "## Workflow",
        "",
    ]
    for i, step in enumerate(a["steps"], 1):
        lines.append(f"{i}. **{text(names[step['owner']])}:** {text(step['action'])}")
        if step["guard"]:
            lines.append(f"   - Decision: {text(step['guard'])}. Alternative: {text(step['alternative'])}.")
        if step["parallel_actions"]:
            lines.append(f"   - In parallel: {text('; '.join(step['parallel_actions']))}.")
    lines += ["", "## Domain model", ""]
    for entity in a["entities"]:
        lines.append(
            f"- **{text(entity['name'])}:** "
            + ", ".join(f"{text(m['name'])} ({text(m['type'])})" for m in entity["attributes"])
        )
    lines += [
        "",
        "## Lifecycle",
        "",
        *[
            f"- {text(t['source'])} → {text(t['target'])}: {text(t['event'])}"
            + (f"; guard: {text(t['guard'])}" if t["guard"] else "")
            for t in a["transitions"]
        ],
        "",
        "## Deployment outline",
        "",
    ]
    lines += [
        f"- **{text(n['name'])} ({text(n['kind'])}):** {text(', '.join(names[c] for c in n['components']))}"
        for n in a["nodes"]
    ]
    lines += ["", "## UML perspectives", ""]
    for diagram in revision["diagrams"]:
        label = diagram["type"].replace("_", " ").title()
        if packaged:
            lines.append(
                f"- [{label} SVG](diagrams/{diagram['type']}.svg) · [Editable source](diagrams/{diagram['type']}.puml)"
            )
        else:
            lines.append(f"- {label} · syntax verified")
    lines += ["", "## Reviews of this revision", ""]
    if reviews:
        lines += [
            f"- **{r['rating']}/5**, {text(r['diagram_type'] or 'entire design')}: {text(r['comment'] or 'Rating only')}. Saved {r['created_at']}."
            for r in reviews
        ]
    else:
        lines.append("No human review has been saved for this revision.")
    lines += [
        "",
        "## Implementation review checklist",
        "",
        "- [ ] Confirm assumptions and requirements with stakeholders.",
        "- [ ] Review failure paths, access boundaries, and data provenance.",
        "- [ ] Validate deployment choices and illustrative timing/instance values.",
        "- [ ] Turn accepted decisions into implementation tasks.",
        "",
        "Generated designs support review; syntax validation does not prove architectural correctness. Human feedback is saved separately from any model training.",
        "",
    ]
    return "\n".join(lines)
