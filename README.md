# АкваМонітор

Моніторинг і короткостроковий прогноз рівня води в річці.
Дані — USGS Water Data API (пост 01646500, Потомак), рівень у метрах.

## Склад команди і ротація ролей

| № | Студент | Тиж. 1 | Тиж. 2 | Тиж. 3 | Тиж. 4 |
|:-:|:--------|:------:|:------:|:------:|:------:|
| 1 | Борута Ростислав   | A   | B   | C   | D+E |
| 2 | Антоняк Констянтин | B   | C   | D+E | A   |
| 3 | Бачинський Олег    | C   | D+E | A   | B   |
| 4 | Казбан Сергій      | D+E | A   | B   | C   |

## Встановлення (Python 3.11+)

```bash
python -m venv .venv
```

Активація: PowerShell — `.venv\Scripts\Activate.ps1`, Git Bash — `source .venv/Scripts/activate`, Linux і macOS — `source .venv/bin/activate`.

```bash
pip install -r requirements.txt
pip install -e .
```

## Тести

```bash
python run_tests.py
```

Або стандартно: `python -m unittest discover -s tests`.

## Команди

```bash
aquamonitor fetch --site 01646500 --period P2D --out data.json
aquamonitor report --input data.json --group-by day --plot levels.png
aquamonitor forecast --input data.json --horizon 12 --plot forecast.png
```

- `fetch` — завантажує рівень води з USGS у JSON-файл;
- `report` — очищує дані й друкує зведення за добу, тиждень чи місяць; `--plot` зберігає гістограму рівнів;
- `forecast` — заповнює пропуски й будує наївний прогноз на `--horizon` годин; `--plot` зберігає графік «факт + прогноз».

Без інтернету можна взяти зразок з репозиторію: `--input tests/data/usgs_sample.json`.
Помилки (немає файлу, зіпсований JSON, неправильний горизонт) дають повідомлення `Error: ...` і код 1. Журнал — `aquamonitor.log`.

## Структура

```
src/aquamonitor/  domain.py dataio.py core.py analytics.py cli.py infra.py __main__.py
tests/            test_<модуль>.py, data/ — зразок відповіді USGS
docs/             spec.md (інтерфейси), HANDOVER-A..E.md (журнали передачі)
run_tests.py      запуск усіх тестів
```
