"""Multipart-upload part planning (pure logic).

Большие загрузки (>5 ГБ single-PUT R2) режутся на части браузером и собираются R2 multipart.
``plan_part_count`` — сколько частей нужно для файла размера ``size`` при ``part_size``.
"""

from __future__ import annotations

from app.storage import MULTIPART_PART_SIZE, plan_part_count


def test_small_file_is_one_part() -> None:
    assert plan_part_count(1, MULTIPART_PART_SIZE) == 1
    assert plan_part_count(MULTIPART_PART_SIZE, MULTIPART_PART_SIZE) == 1


def test_exact_multiple() -> None:
    assert plan_part_count(3 * MULTIPART_PART_SIZE, MULTIPART_PART_SIZE) == 3


def test_remainder_rounds_up() -> None:
    assert plan_part_count(2 * MULTIPART_PART_SIZE + 1, MULTIPART_PART_SIZE) == 3


def test_zero_or_negative_is_one_part() -> None:
    # Defensive: a bad/zero size still yields a valid single-part plan, never 0 parts.
    assert plan_part_count(0, MULTIPART_PART_SIZE) == 1
    assert plan_part_count(-10, MULTIPART_PART_SIZE) == 1
