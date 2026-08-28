<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/AdsPower-Anti--Detect-FF6B35?style=flat-square&logo=browserstack&logoColor=white" />
  <img src="https://img.shields.io/badge/Playwright-1.40+-2EAD33?style=flat-square&logo=playwright&logoColor=white" />
  <img src="https://img.shields.io/badge/hCaptcha-Bypass-FF4444?style=flat-square&logo=probot&logoColor=white" />
</p>

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗               ║
║   ██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝               ║
║   ██████╔╝███████║███████║██╔██╗ ██║   ██║                  ║
║   ██╔══██╗██╔══██║██╔══██║██║╚██╗██║   ██║                  ║
║   ██║  ██║██║  ██║██║  ██║██║ ╚████║   ██║                  ║
║   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝                  ║
║                                                              ║
║         P A S S   C H A N G E R   v2.0                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

<br/>

> *Меняй пароли быстрее, чем они умирают.*

<br/>

## ЧТО ЭТО ДЕЛАЕТ

```
┌─────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  creditials │────┐    │   AdsPower API   │         │   id.rambler.ru  │
│  .txt       │    │    │  (N профилей)    │         │   /login-20      │
│             │    │    │                  │         │   /account/      │
│ email:pass  │    ▼    │  ┌────────────┐  │         │   change-password│
└─────────────┘    ├───▶│  │  Changer   │──┼────────▶│                  │
                   │    │  │            │  │  CDP    │  hCaptcha → реши │
                   │    │  │  Логин     │  │         │  Нажми "Сохранить"│
                   │    │  │  Смена     │  │         └──────────────────┘
                   │    │  │  Проверка  │  │                  │
                   │    │  └────────────┘  │                  │
                   │    └──────────────────┘                  │
                   │              │                           │
                   ▼              ▼                           ▼
            ┌──────────┐  ┌──────────┐              ┌───────────────┐
            │ old_log. │  │ new_log. │              │ creditials.txt│
            │          │  │          │              │   (успешные   │
            │pass:mail │  │pass:mail │              │  удалены)     │
            └──────────┘  └──────────┘              └───────────────┘
```

<br/>

## БЫСТРЫЙ СТАРТ

**1.** Положи почты в `creditials.txt`:
```
user1@rambler.ru:OldPassword123
user2@rambler.ru:AnotherOldPass
```

**2.** Создай профили в AdsPower с прокси (SOCKS5/HTTP). Заметки заполнять не нужно — программа мэтчит по email.

**3.** Запусти:
```bash
python changer.py --change 10 --worker 1
```

**4.** Когда появится капча в браузере — реши, нажми Enter в консоли.

**5.** Готово. Новые пароли в `new_logins.txt`, старые в `old_logins.txt`. Успешные аккаунты удалены из `creditials.txt`.

<br/>

## КОМАНДЫ

```
python changer.py --help
```

| Флаг | Зачем | Пример |
|------|-------|--------|
| `--change N` | Сколько почт менять | `--change 5` |
| `--worker N` | Потоков (по умолчанию 3) | `--worker 1` |
| `--dry-run` | Показать план без действий | `--dry-run` |
| `--skip-check` | Без IMAP-проверки | `--skip-check` |
| `--api URL` | AdsPower API (default: localhost:50325) | `--api http://...` |

```bash
# Все почты из файла
python changer.py

# Первые 5, 1 поток, без проверки
python changer.py --change 5 --worker 1 --skip-check

# Посмотреть что будет
python changer.py --dry-run --change 3
```

<br/>

## ВЫХОДНЫЕ ФАЙЛЫ

| Файл | Формат | Что внутри |
|------|--------|------------|
| `old_logins.txt` | `login:password` | Старые пароли обработанных |
| `new_logins.txt` | `login:password` | Новые пароли успешных |
| `errors.txt` | `login:password \| ошибка` | Что пошло не так |
| `creditials.txt` | `login:password` | Оставшиеся (успешные удалены) |

<br/>

## ТРЕБОВАНИЯ

```
Python 3.10+  |  AdsPower запущен  |  Playwright + Chromium
```

```bash
pip install playwright requests colorama
playwright install chromium
```

<br/>

## FAQ

<details>
<summary><b>Почему не обычный Playwright?</b></summary>
<br/>
Rambler ставит hCaptcha + детектит автоматизацию. AdsPower даёт уникальный отпечаток браузера + прокси для каждого аккаунта. Без AdsPower id.rambler.ru покажет пустую страницу.
</details>

<details>
<summary><b>Как работает капча?</b></summary>
<br/>
Скрипт открывает браузер, ты видишь форму "Смена пароля" с hCaptcha. Кликаешь "Я человек", решаешь, жмёшь Enter в консоли. Скрипт нажмёт "Сохранить" автоматически.
</details>

<details>
<summary><b>Профилей меньше чем почт?</b></summary>
<br/>
Программа возьмёт столько профилей сколько есть. Остальные пропустит.
</details>

<details>
<summary><b>Аккаунт заблокирован?</b></summary>
<br/>
В логах будет `FAIL (Аккаунт заблокирован)`. Аккаунт останется в `creditials.txt` для повторной попытки.
</details>

<details>
<summary><b>Удалять успешные из creditials?</b></summary>
<br/>
Да. После успешной смены пароля аккаунт автоматически удаляется из `creditials.txt`. Фейлы остаются — можно перезапустить и попробовать снова.
</details>

<br/>

---

<p align="center">
  <sub>Сделано потому что Rambler-почты умирают через месяц. Теперь не умирают.</sub>
</p>
