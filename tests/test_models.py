import copy

import pytest
from pydantic import ValidationError

from app.models import Architecture, GenerateRequest
from app.sample import BASE


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a["connections"][0].update(source="missing"),
        lambda a: a["relations"][0].update(target="missing"),
        lambda a: a["steps"][0].update(owner="missing"),
        lambda a: a["nodes"][0].update(components=["missing"]),
        lambda a: a["transitions"][0].update(source="missing"),
        lambda a: a["timelines"][0].update(component="missing"),
        lambda a: a["components"].append(a["components"][0]),
        lambda a: a["timelines"][0]["ticks"].reverse(),
        lambda a: a["components"][2]["ports"][0].update(part="missing"),
        lambda a: a["steps"][0].update(guard="A decision?"),
        lambda a: a["interactions"][0].update(fragment="loop"),
    ],
)
def test_referential_integrity(mutation):
    design = copy.deepcopy(BASE)
    mutation(design)
    with pytest.raises(ValidationError):
        Architecture.model_validate(design)


def test_type_aliases_deduplicate_after_normalizing():
    req = GenerateRequest(
        prompt="A sufficiently clear brief", diagram_types=["sequential", "sequence", "component"]
    )
    assert len(req.diagram_types) == 2
    assert str(req.request_id)
