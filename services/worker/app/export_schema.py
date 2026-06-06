"""Codegen: app.models (Pydantic) → packages/shared/contract.json (JSON Schema).

Запуск: ``uv run python -m app.export_schema`` (см. рецепт ``just types``).

Детерминированно: сортированные ключи, LF, финальный перевод строки — иначе
anti-drift гейт (`just check`) будет дёргаться на разнице форматирования.

НЕ редактируем contract.json руками: правим models.py и перегенерим (`just types`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.models import (
    Clip,
    ClipOut,
    CropWindow,
    Job,
    Metrics,
    Segment,
    Transcript,
    Word,
)

# Только BaseModel-модели. Enums (ClipType/JobStatus/SourceKind) попадут в $defs
# автоматически — на них ссылаются модели. Явная аннотация — чтобы mypy видел
# type[BaseModel], а не ModelMetaclass.
_MODELS: list[type[BaseModel]] = [
    Word,
    Transcript,
    Segment,
    CropWindow,
    Clip,
    ClipOut,
    Metrics,
    Job,
]

# app/export_schema.py → parents: [0]=app [1]=worker [2]=services [3]=<repo root>
CONTRACT_PATH = Path(__file__).resolve().parents[3] / "packages" / "shared" / "contract.json"


def _strip_titles(node: Any) -> None:
    """Рекурсивно удалить ключи "title".

    Pydantic вешает title на каждое поле; json2ts из-за этого плодит мусорные
    алиасы (``export type H = number``) и коллизии имён. Без title поля инлайнятся
    (``end: number``), а имена интерфейсов берутся из ключей $defs.
    """
    if isinstance(node, dict):
        node.pop("title", None)
        for v in node.values():
            _strip_titles(v)
    elif isinstance(node, list):
        for v in node:
            _strip_titles(v)


def build_contract() -> dict[str, Any]:
    """Собрать единую JSON Schema со всеми контрактами в $defs.

    Чтобы json-schema-to-typescript сгенерил тип для КАЖДОГО контракта, ссылаемся
    на все $defs из properties корневого объекта (иначе несвязанные модели могут
    выпасть из вывода).
    """
    mode: Literal["serialization"] = "serialization"
    _, schema = models_json_schema(
        [(m, mode) for m in _MODELS],
        ref_template="#/$defs/{model}",
        title="ClipFlowContract",
    )
    _strip_titles(schema)
    defs: dict[str, Any] = schema.get("$defs", {})
    schema["title"] = "ClipFlowContract"  # вернуть корневой title (имя root-типа в TS)
    schema["type"] = "object"
    schema["properties"] = {name: {"$ref": f"#/$defs/{name}"} for name in sorted(defs)}
    schema["additionalProperties"] = False
    return schema


def main() -> None:
    parent = CONTRACT_PATH.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"packages/shared не найден: {parent}")
    contract = build_contract()
    text = json.dumps(contract, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    CONTRACT_PATH.write_text(text, encoding="utf-8", newline="\n")
    n_defs = len(contract.get("$defs", {}))
    print(f"wrote {CONTRACT_PATH} ({len(text)} bytes, {n_defs} defs)")


if __name__ == "__main__":
    main()
