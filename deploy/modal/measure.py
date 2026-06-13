"""Тонкая обёртка для замера тяжёлого воркера на Modal — переиспользует app.py.

Логика замера живёт в app.py (правило «без дублей»): функция reframe_and_render_sample
на GPU + local_entrypoint measure(). Этот файл — просто удобная точка входа, чтобы
команда читалась как «замер»:

    modal run deploy/modal/measure.py

делает то же, что `modal run deploy/modal/app.py::measure`. Образ, GPU, сэмпл-клип и
расчёт стоимости — всё из app.py.
"""

from __future__ import annotations

# Реэкспорт App, GPU-функции и энтрипоинта. `modal run measure.py` подхватит
# тот же App и зарегистрированную функцию — отдельного дубля кода нет.
from app import app, measure, reframe_and_render_sample  # noqa: F401
