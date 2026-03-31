import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from engine import load_data, generate_document
from extractor import extract
from validator import validate, print_results


def main():
    parser = argparse.ArgumentParser(
        description="Генерация тендерных документов по шаблонам и данным JSON."
    )
    parser.add_argument(
        "--profile",
        default="data/company_profile.json",
        help="Путь к JSON-профилю компании (по умолчанию: data/company_profile.json)",
    )
    parser.add_argument(
        "--tender",
        default="data/tender.json",
        help="Путь к JSON с данными тендера (по умолчанию: data/tender.json)",
    )
    parser.add_argument(
        "--calc",
        default="data/calc.json",
        help="Путь к JSON с расчётом цены (по умолчанию: data/calc.json)",
    )
    parser.add_argument(
        "--from-docx",
        metavar="DOCX",
        help="Извлечь данные тендера из входящего DOCX и сохранить в data/tender_extracted.json",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Пропустить валидацию входных данных (для тестовых/синтетических данных)",
    )
    args = parser.parse_args()

    # Шаг 1: если передан входящий DOCX — извлечь в отдельный файл, не перезаписывая --tender
    if args.from_docx:
        extracted_path = "data/tender_extracted.json"
        print(f"Извлечение данных из {args.from_docx}...")
        result = extract(args.from_docx)
        with open(extracted_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Сохранено: {extracted_path}")
        print(f"Внимание: поля с null требуют ручного заполнения перед запуском генерации.")
        args.tender = extracted_path

    # Шаг 2: загрузить данные
    context = load_data(args.profile, args.tender, args.calc)

    # Шаг 3: валидация — при ошибках остановиться
    if args.no_validate:
        print("Валидация пропущена (--no-validate).")
    else:
        errors, warnings = validate(context)
        print_results(errors, warnings)
        if errors:
            print(f"\nГенерация прервана: {len(errors)} ошибок.")
            sys.exit(1)

    # Шаг 4: генерация всех документов по маппингам из mappings/
    mappings = sorted(Path("mappings").glob("*.yaml"))
    if not mappings:
        print("Ошибка: папка mappings/ пуста или не найдена.")
        sys.exit(1)

    print()
    for mapping in mappings:
        generate_document(str(mapping), context)

    print("\nГотово.")


if __name__ == "__main__":
    main()
