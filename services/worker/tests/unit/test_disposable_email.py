"""Анти-абьюз: блок одноразовых/temp-mail доменов (billing.is_disposable_email, PURE).

Бесплатный план (2 видео) абьюзят пачками одноразовых ящиков. is_disposable_email —
чистая проверка домена по денилисту общих temp-mail сервисов. Регистронезависима,
устойчива к пустому/битому вводу, матчит и поддомены сервиса (mail.guerrillamail.com).
Денилист — стартовый, расширяемый (одна строка в DISPOSABLE_EMAIL_DOMAINS).
"""

from __future__ import annotations

import pytest

from app.billing import DISPOSABLE_EMAIL_DOMAINS, is_disposable_email


class TestIsDisposableEmail:
    @pytest.mark.parametrize(
        "email",
        [
            "abuser@mailinator.com",
            "x@guerrillamail.com",
            "y@10minutemail.com",
            "z@temp-mail.org",
            "q@getnada.com",
            "w@yopmail.com",
            "ABUSER@MAILINATOR.COM",  # регистр не важен
            "  user@yopmail.com  ",  # пробелы по краям обрезаются
        ],
    )
    def test_known_disposable_blocked(self, email: str) -> None:
        assert is_disposable_email(email) is True

    @pytest.mark.parametrize(
        "email",
        [
            "real.person@gmail.com",
            "founder@quip.ink",
            "dev@example.com",
            "name@company.co.uk",
        ],
    )
    def test_real_domains_allowed(self, email: str) -> None:
        assert is_disposable_email(email) is False

    def test_subdomain_of_disposable_service_blocked(self) -> None:
        # Temp-mail сервисы раздают поддомены (mail.guerrillamail.com, www.yopmail.com) —
        # их тоже режем (матч по суффиксу домена, не точное равенство).
        assert is_disposable_email("a@mail.guerrillamail.com") is True
        assert is_disposable_email("b@www.yopmail.com") is True

    def test_lookalike_not_matched_as_substring(self) -> None:
        # "notyopmail.com" — НЕ поддомен yopmail.com → не блокируем (суффикс по границе точки).
        assert is_disposable_email("c@notyopmail.com") is False
        assert is_disposable_email("d@mailinator.com.evil.example") is False

    @pytest.mark.parametrize("bad", ["", "   ", "no-at-sign", "@nodomain", "user@", None])
    def test_malformed_input_is_not_disposable(self, bad: object) -> None:
        # Битый ввод не «одноразовый» (валидность email проверяет signup-флоу/Supabase,
        # а не эта функция). Никаких исключений — чистый bool.
        assert is_disposable_email(bad) is False  # type: ignore[arg-type]

    def test_denylist_is_nonempty_and_lowercase(self) -> None:
        assert len(DISPOSABLE_EMAIL_DOMAINS) >= 10
        assert all(d == d.lower() and "@" not in d for d in DISPOSABLE_EMAIL_DOMAINS)
