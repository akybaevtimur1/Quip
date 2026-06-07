"""Тесты pure-логики оценки качества (рубрика §7.1): бакет клипа + метрика Q."""

from app.eval import clip_bucket, compute_q


def _scores(**over: int) -> dict[str, int]:
    base = {c: 1 for c in ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8")}
    base.update(over)
    return base


class TestClipBucket:
    def test_all_pass_is_usable(self) -> None:
        assert clip_bucket(_scores()) == "usable"

    def test_killer_c1_is_reject(self) -> None:
        assert clip_bucket(_scores(c1=0)) == "reject"  # не standalone — killer

    def test_killer_c5_is_reject(self) -> None:
        assert clip_bucket(_scores(c5=0)) == "reject"  # лицо обрезано — killer

    def test_killer_c6_is_reject(self) -> None:
        assert clip_bucket(_scores(c6=0)) == "reject"  # субтитры врут — killer

    def test_one_trimmable_fail_high_total_usable(self) -> None:
        # C3 провален (тримабельный), total=7, без killers → usable
        assert clip_bucket(_scores(c3=0)) == "usable"

    def test_two_trimmable_fails_is_fixable(self) -> None:
        # C3+C8 провалены (оба тримабельные), total=6, без killers → fixable
        assert clip_bucket(_scores(c3=0, c8=0)) == "fixable"

    def test_nontrimmable_fail_is_reject(self) -> None:
        # C7 (синк) провален — не тримабельный, total=6 → reject
        assert clip_bucket(_scores(c7=0, c8=0)) == "reject"

    def test_low_total_is_reject(self) -> None:
        assert clip_bucket(_scores(c2=0, c3=0, c4=0, c7=0, c8=0)) == "reject"  # total=3


class TestComputeQ:
    def test_q_is_usable_plus_fixable_over_total(self) -> None:
        assert compute_q(["usable", "fixable", "reject", "reject"]) == 0.5

    def test_all_usable(self) -> None:
        assert compute_q(["usable", "usable"]) == 1.0

    def test_empty_is_zero(self) -> None:
        assert compute_q([]) == 0.0
