"""JobError — кросс-контейнерная (де)сериализация (Modal pickle round-trip).

Воспроизводит боевой провал: дочерний клип-контейнер пиклит JobError, координатор его
распикливает. Если в ``args`` не лежат РОВНО ``(stage, reason)``, приёмник зовёт
``JobError(<один-стринг>)`` → «missing 1 required positional argument (reason)»
(Modal: «Could not deserialize remote exception»).
"""

from __future__ import annotations

import copy
import pickle

from app.errors import JobError


def test_joberror_public_api_unchanged() -> None:
    e = JobError("render", "boom")
    assert e.stage == "render"
    assert e.reason == "boom"
    assert str(e) == "[render] boom"


def test_joberror_pickle_round_trip_keeps_stage_and_reason() -> None:
    # Это РОВНО воспроизводит провал Modal-кросс-контейнера локально.
    restored = pickle.loads(pickle.dumps(JobError("render", "boom")))
    assert isinstance(restored, JobError)
    assert restored.stage == "render"
    assert restored.reason == "boom"
    assert str(restored) == "[render] boom"


def test_joberror_args_carry_both_positionals() -> None:
    # BaseException реконструируется как ``cls(*args)`` → в args ОБА позиционных.
    e = JobError("limit", "Quota exceeded")
    assert e.args == ("limit", "Quota exceeded")
    # Прямая реконструкция тем же контрактом, что использует пиклер.
    reconstructed = JobError(*e.args)
    assert reconstructed.stage == "limit"
    assert reconstructed.reason == "Quota exceeded"


def test_joberror_reduce_targets_two_arg_init() -> None:
    e = JobError("import", "no source")
    cls, args = e.__reduce__()
    assert cls is JobError
    assert args == ("import", "no source")
    rebuilt = cls(*args)
    assert (rebuilt.stage, rebuilt.reason) == ("import", "no source")


def test_joberror_deepcopy_round_trip() -> None:
    # deepcopy идёт через __reduce__ — ещё один путь реконструкции (страховка).
    e = copy.deepcopy(JobError("render", "ffmpeg 0 frames"))
    assert e.stage == "render"
    assert e.reason == "ffmpeg 0 frames"
