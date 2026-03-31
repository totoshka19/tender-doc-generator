from datetime import date, datetime


def _check_inn(inn: str) -> str | None:
    """Проверяет ИНН юрлица (10 цифр) по алгоритму ФНС. Возвращает текст ошибки или None."""
    if not isinstance(inn, str) or not inn.isdigit():
        return f"ИНН '{inn}' содержит нецифровые символы"
    if len(inn) != 10:
        return f"ИНН '{inn}' должен содержать 10 цифр (получено {len(inn)})"
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    check = sum(w * int(d) for w, d in zip(weights, inn)) % 11 % 10
    if check != int(inn[9]):
        return f"ИНН '{inn}' не прошёл проверку контрольной суммы"
    return None


def _check_kpp(kpp: str) -> str | None:
    if not isinstance(kpp, str) or not kpp.isdigit():
        return f"КПП '{kpp}' содержит нецифровые символы"
    if len(kpp) != 9:
        return f"КПП '{kpp}' должен содержать 9 цифр (получено {len(kpp)})"
    return None


def _check_bik(bik: str) -> str | None:
    if not isinstance(bik, str) or not bik.isdigit():
        return f"БИК '{bik}' содержит нецифровые символы"
    if len(bik) != 9:
        return f"БИК '{bik}' должен содержать 9 цифр (получено {len(bik)})"
    if not bik.startswith("04"):
        return f"БИК '{bik}' должен начинаться с '04'"
    return None


def _check_ogrn(ogrn: str) -> str | None:
    if not isinstance(ogrn, str) or not ogrn.isdigit():
        return f"ОГРН '{ogrn}' содержит нецифровые символы"
    if len(ogrn) not in (13, 15):
        return f"ОГРН '{ogrn}' должен содержать 13 или 15 цифр (получено {len(ogrn)})"
    return None


def _check_bid_deadline(bid_deadline: str) -> str | None:
    """Проверяет, что дата подачи предложений не в прошлом. Формат: 'DD.MM.YYYY ...'."""
    if not isinstance(bid_deadline, str):
        return "bid_deadline отсутствует или не является строкой"
    try:
        date_part = bid_deadline.split()[0]
        deadline_date = datetime.strptime(date_part, "%d.%m.%Y").date()
    except (ValueError, IndexError):
        return f"bid_deadline '{bid_deadline}' — не удалось разобрать дату (ожидается ДД.ММ.ГГГГ)"
    if deadline_date < date.today():
        return f"bid_deadline '{bid_deadline}' — срок подачи уже истёк"
    return None


def _check_calc(calc: dict) -> list[str]:
    """Проверяет арифметическую согласованность сумм в calc."""
    errors = []
    items = calc.get("items", [])
    vat_rate = calc.get("vat_rate")
    subtotal = calc.get("subtotal_wo_vat")
    vat_amount = calc.get("vat_amount")
    total = calc.get("total_with_vat")

    if not all(isinstance(v, (int, float)) for v in [vat_rate, subtotal, vat_amount, total]):
        errors.append("calc.json: отсутствуют или некорректны числовые поля итогов")
        return errors

    for i, item in enumerate(items):
        price = item.get("unit_price_wo_vat")
        qty_val = None
        line_total = item.get("line_total_wo_vat")
        if not all(isinstance(v, (int, float)) for v in [price, line_total]):
            errors.append(f"calc.items[{i}]: некорректные числовые поля")
            continue
        if price <= 0:
            errors.append(f"calc.items[{i}]: цена unit_price_wo_vat должна быть положительной")
        if line_total <= 0:
            errors.append(f"calc.items[{i}]: сумма line_total_wo_vat должна быть положительной")

    expected_subtotal = round(sum(item.get("line_total_wo_vat", 0) for item in items), 2)
    if abs(round(subtotal, 2) - expected_subtotal) > 0.01:
        errors.append(
            f"calc.json: subtotal_wo_vat={subtotal} не совпадает "
            f"с суммой позиций {expected_subtotal}"
        )

    expected_vat = round(subtotal * vat_rate, 2)
    if abs(round(vat_amount, 2) - expected_vat) > 0.01:
        errors.append(
            f"calc.json: vat_amount={vat_amount} не совпадает "
            f"с subtotal × vat_rate ({expected_vat})"
        )

    expected_total = round(subtotal + vat_amount, 2)
    if abs(round(total, 2) - expected_total) > 0.01:
        errors.append(
            f"calc.json: total_with_vat={total} не совпадает "
            f"с subtotal + vat ({expected_total})"
        )

    return errors


def validate(context: dict) -> tuple[list[str], list[str]]:
    """
    Проверяет входные данные перед генерацией.
    Возвращает (errors, warnings). Ошибки блокируют генерацию, предупреждения — нет.
    """
    errors: list[str] = []
    warnings: list[str] = []

    profile = context.get("profile", {})
    tender = context.get("tender", {})
    calc = context.get("calc", {})

    company = profile.get("company", {})
    bank = profile.get("bank", {})

    # --- Реквизиты компании ---
    for field, checker, label in [
        (company.get("inn"), _check_inn, "company.inn"),
        (company.get("kpp"), _check_kpp, "company.kpp"),
        (company.get("ogrn"), _check_ogrn, "company.ogrn"),
        (bank.get("bik"), _check_bik, "bank.bik"),
    ]:
        if field is None:
            warnings.append(f"{label} отсутствует в profile")
        else:
            err = checker(field)
            if err:
                errors.append(err)

    # --- Дата подачи предложений ---
    bid_deadline = tender.get("bid_deadline")
    if bid_deadline is None:
        warnings.append("tender.bid_deadline отсутствует")
    else:
        err = _check_bid_deadline(bid_deadline)
        if err:
            errors.append(err)

    # --- Срок действия предложения ---
    validity = tender.get("offer_validity_days")
    if validity is None:
        warnings.append("tender.offer_validity_days отсутствует")
    elif not isinstance(validity, int) or validity <= 0:
        errors.append(f"tender.offer_validity_days='{validity}' должен быть положительным целым числом")

    # --- Арифметика calc ---
    errors.extend(_check_calc(calc))

    return errors, warnings


def print_results(errors: list[str], warnings: list[str]) -> None:
    if warnings:
        print("ПРЕДУПРЕЖДЕНИЯ:")
        for w in warnings:
            print(f"  [!] {w}")
    if errors:
        print("ОШИБКИ:")
        for e in errors:
            print(f"  [X] {e}")
    if not errors and not warnings:
        print("Валидация пройдена.")
