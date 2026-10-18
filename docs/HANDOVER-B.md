# Handover Document — Role B (Data: parsing, files, streams)

---

## Тиждень 1
**Date:** 2026-10-18
**Author:** Антоняк Констянтин

## 1. Зроблено
* Закрито перший пункт переліку ролі B: «Клієнт зовнішнього джерела: HTTP-запит, розбір JSON, перетворення у структури ролі A».
* `src/aquamonitor/dataio.py`: `ParseError(HydroError)`, `build_usgs_url`, `fetch_usgs_json`, `parse_usgs_json`.
* `fetch_usgs_json(site, parameter, period)` робить GET-запит до USGS Water Data API через `urllib`; помилки мережі й тайм-аут стають `ParseError`.
* `parse_usgs_json(json_str)` перетворює відповідь API (GeoJSON, поле `features`) у `list[Observation]`: час у UTC, `null` стає `None`, результат відсортовано за `(sensor_id, час)`.
* Перевірено живий запит (пост 01646500, параметр 00065, 6 годин): отримано 68 записів. USGS Water Data API доступний.
* 11 тестів у `tests/test_dataio.py` (усі зелені), мережу не використовують. На помилкові дані: порожній рядок, не JSON, немає `features`, немає `time`, поганий час, нечислове значення, не рядок на вході, збій мережі. Зразок реальної відповіді: `tests/data/usgs_sample.json`.

## 2. Не зроблено
* Парсер журналів регулярними виразами, очищення даних, генератор `stream_observations`, менеджер `ArchiveReader`, генератор синтетичних даних, експорт у CSV/JSON (наступні пункти переліку).
* Формат RDB не підтримується: завдання вимагає «JSON/RDB», ми взяли JSON, бо старий сервіс USGS виводиться з експлуатації.
* NOAA NCEI і Kaggle не перевірялися.

## 3. Ухвалені рішення
* Використано новий USGS Water Data API (`api.waterdata.usgs.gov/ogcapi/v1`), а не старий `waterservices.usgs.gov`.
* `sensor_id` має вигляд `<пост>-<параметр>`, наприклад `USGS-01646500-00065`.
* Час без зсуву вважається UTC; усі `Observation` повертаються з часом UTC.
* `ParseError` використовується і для помилок читання (мережа), і для помилок розбору, як сказано в `spec.md`.

## 4. Проблеми
* `Observation` не має поля для статусу даних (`Provisional`/`Approved`), тому API-шний статус не зберігається. Потрібне рішення ролі A.
* `fetch_usgs_json` читає лише першу сторінку (до 10 000 записів). Тиждень 15-хвилинних даних це близько 700, але місяць уже не вміститься.
* Якщо в відповіді кілька параметрів, функція повертає їх разом; `Series` приймає лише один `sensor_id`, тому треба відфільтрувати за `sensor_id`.
* `parse_usgs_json` і `fetch_usgs_json` треба додати в `docs/spec.md` (сигнатури, формат `sensor_id`).

## 5. Далі
* Парсер текстових журналів гідропоста регулярним виразом (дата, код поста, значення, прапорець якості). Формат рядка спершу зафіксувати в `docs/spec.md`.
* Очищення: виявлення викидів, уніфікація часу, журнал відкинутих записів (`clean_observations`).

## 6. Обережно
* Не змінювати сигнатури `fetch_usgs_json` і `parse_usgs_json` без запиту на злиття, який переглядають усі: від них залежить `cli.py`.
* `parse_usgs_json` повертає всі сенсори разом; перед створенням `Series` відфільтруйте один `sensor_id`.

## 7. Як запустити
1. Переконайтеся, що ви в корені репозиторію й активовано віртуальне середовище.
2. Запуск тестів:
   ```powershell
   $env:PYTHONPATH="src"
   python -m unittest tests.test_dataio -v
   ```
3. Приклад використання:
   ```python
   from aquamonitor.dataio import fetch_usgs_json, parse_usgs_json
   observations = parse_usgs_json(fetch_usgs_json("01646500", "00065", "PT6H"))
   ```

---
