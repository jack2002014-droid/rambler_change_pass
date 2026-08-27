<div align="center">

# 🔐 Rambler Pass Changer

**Автоматическая смена паролей Rambler почт через AdsPower**

Покупаешь почты — они через месяц умирают. Эта штука меняет пароли автоматически.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![AdsPower](https://img.shields.io/badge/AdsPower-Anti--Detect-FF6B35?style=for-the-badge&logo=browserstack&logoColor=white)](https://adspower.com)

</div>

---

## Как работает

```
creditials.txt          AdsPower (10 профилей с прокси)
  email:pass                    │
       │                        │
       ▼                        ▼
  ┌─────────────────────────────────┐
  │         Rambler Changer         │
  │                                 │
  │  1. Берёт первые N почт         │
  │  2. Берёт первые N профилей     │
  │  3. Сопоставляет 1:1            │
  │  4. IMAP-проверка (живая ли?)   │
  │  5. Запускает AdsPower браузер  │
  │  6. Логинится → Меняет пароль   │
  │  7. Уникальный пароль 12-16     │
  └─────────────────────────────────┘
       │              │
       ▼              ▼
  old_logins.txt   new_logins.txt
```

---

## Быстрый старт

### 1. Создай почты в `creditials.txt`

```
user1@rambler.ru:Password123
user2@rambler.ru:AnotherPass
user3@rambler.ru:ThirdPass
```

### 2. Создай профили в AdsPower

- Открой AdsPower → Профили → Создать
- Добавь прокси (SOCKS5/HTTP) каждому
- **Не нужно** заполнять заметки — программа сама всё найдёт

### 3. Запусти

```bash
# Меняем 10 почт, 3 потока
python changer.py --change 10 --worker 3

# Все почты из файла
python changer.py

# Посмотреть что будет (без действий)
python changer.py --dry-run --change 5
```

---

## Команды

| Флаг | Описание | Пример |
|------|----------|--------|
| `--change N` | Сколько почт менять | `--change 10` |
| `--worker N` | Потоков одновременно | `--worker 3` |
| `--dry-run` | План без действий | `--dry-run` |
| `--skip-check` | Без IMAP-проверки | `--skip-check` |
| `--api URL` | AdsPower API | `--api http://localhost:50325` |

```bash
# Примеры
python changer.py --change 5 --worker 2
python changer.py --dry-run --change 20
python changer.py --skip-check --change 3
```

---

## Выходные файлы

| Файл | Что внутри |
|------|-----------|
| `old_logins.txt` | `email:старый_пароль` |
| `new_logins.txt` | `email:новый_пароль` |
| `errors.txt` | Лог ошибок |

---

## Требования

- **Python** 3.10+
- **AdsPower** — запущен с профилями и прокси
- **Playwright** + Chromium

```bash
pip install playwright requests colorama imap-tools
playwright install chromium
```

---

## FAQ

**Капча появилась?**
Программа остановится и попросит решить вручную в открытом браузере. После решения нажми Enter.

**Почему AdsPower?**
Rambler ставит hCaptcha. Обычный Playwright не пройдёт. AdsPower даёт уникальный отпечаток + прокси для каждого аккаунта.

**Профилей меньше чем почт?**
Программа возьмёт столько профилей сколько есть. Остальные пропустит.

---

<div align="center">

**Сделано с 🖤**

</div>
