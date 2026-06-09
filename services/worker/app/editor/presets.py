"""Style-пресеты (спека §9): apply_preset (PURE) + чтение/запись глобального presets.json."""

from __future__ import annotations

import json
from pathlib import Path

from app.models import CaptionPreset, ClipEdit
from app.run import DATA_ROOT


def apply_preset(edit: ClipEdit, preset: CaptionPreset) -> ClipEdit:
    """Записать style+highlight пресета в captions клипа. Реплики не трогает. PURE."""
    captions = edit.captions.model_copy(
        update={"style": preset.style, "highlight": preset.highlight}
    )
    return edit.model_copy(update={"captions": captions})


def _presets_path() -> Path:
    return DATA_ROOT / "presets.json"


def list_presets() -> list[CaptionPreset]:
    path = _presets_path()
    if not path.exists():
        return []
    return [CaptionPreset.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def save_preset(preset: CaptionPreset) -> CaptionPreset:
    """Добавить/заменить пресет по id, записать файл."""
    items = [p for p in list_presets() if p.id != preset.id]
    items.append(preset)
    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        json.dumps([p.model_dump() for p in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preset


def get_preset(preset_id: str) -> CaptionPreset | None:
    return next((p for p in list_presets() if p.id == preset_id), None)
