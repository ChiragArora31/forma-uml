from uuid import uuid4

import pytest

from app.store import Conflict, Store


def test_generation_leases_are_shared_across_store_instances(tmp_path, admission_database):
    first = Store(tmp_path / "state.sqlite", database_url=admission_database)
    second = Store(tmp_path / "state.sqlite", database_url=admission_database)
    request = str(uuid4())
    first.claim_generation("owner", request)
    with pytest.raises(Conflict, match="already in progress"):
        second.claim_generation("owner", str(uuid4()))
    second.release_generation("owner", "different-request")
    with pytest.raises(Conflict):
        second.claim_generation("owner", str(uuid4()))
    first.release_generation("owner", request)
    second.claim_generation("owner", str(uuid4()))


def test_global_slots_and_expired_leases(tmp_path, admission_database):
    store = Store(tmp_path / "state.sqlite", database_url=admission_database)
    store.claim_generation("first", str(uuid4()), maximum=1)
    with pytest.raises(Conflict, match="workers are busy"):
        store.claim_generation("second", str(uuid4()), maximum=1)
    with store.db() as db:
        db.execute("UPDATE generation_leases SET expires_at=0")
    store.claim_generation("second", str(uuid4()), maximum=1)
