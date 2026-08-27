import argparse
import imaplib
import os
import sys
import random
import string
import time
import json
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import colorama
    colorama.init()
    C_GREEN = '\033[92m'
    C_RED = '\033[91m'
    C_CYAN = '\033[96m'
    C_YELLOW = '\033[93m'
    C_RESET = '\033[0m'
except ImportError:
    C_GREEN = C_RED = C_CYAN = C_YELLOW = C_RESET = ''

parser = argparse.ArgumentParser(description='Смена паролей Rambler через AdsPower')
parser.add_argument('input', nargs='?', default='creditials.txt', help='Файл с почтами (email:password)')
parser.add_argument('--change', type=int, default=0, help='Сколько почт менять (0 = все)')
parser.add_argument('--worker', type=int, default=3, help='Потоков (по умолчанию 3)')
parser.add_argument('--dry-run', action='store_true', help='Показать план без действий')
parser.add_argument('--skip-check', action='store_true', help='Пропустить IMAP-проверку')
parser.add_argument('--api', default='http://localhost:50325', help='AdsPower API (по умолчанию localhost:50325)')
args = parser.parse_args()

THREADS = args.worker
CREDENTIALS_FILE = args.input
ADS_API = args.api
IMAP_HOST = 'imap.rambler.ru'
IMAP_PORT = 993
TIMEOUT = 20

valid_lock = threading.Lock()
success_count = 0
fail_count = 0
skip_count = 0
checked_count = 0
total = 0


def gen_password(length=None):
    if length is None:
        length = random.randint(12, 16)
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def check_imap(email, password):
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=TIMEOUT)
        imap.login(email, password)
        imap.logout()
        return True
    except Exception:
        return False


def load_accounts():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f'{C_RED}Файл {CREDENTIALS_FILE} не найден!{C_RESET}')
        print(f'Создай файл {CREDENTIALS_FILE} в формате: email:password')
        sys.exit(1)
    accounts = []
    with open(CREDENTIALS_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(':', 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                continue
            accounts.append((parts[0], parts[1]))
    if not accounts:
        print(f'{C_RED}Нет аккаунтов в {CREDENTIALS_FILE}!{C_RESET}')
        sys.exit(1)
    return accounts


def generate_unique_passwords(count, existing):
    passwords = set()
    while len(passwords) < count:
        p = gen_password()
        if p not in existing:
            passwords.add(p)
            existing.add(p)
    return list(passwords)


def get_adspower_profiles(count):
    """Берём первые N профилей из AdsPower"""
    profiles = []
    page = 1
    while len(profiles) < count:
        try:
            resp = requests.get(f'{ADS_API}/api/v1/user/list', params={
                'page': page, 'page_size': min(100, count - len(profiles) + 10)
            }, timeout=10)
            data = resp.json()
            if data.get('code') != 0:
                break
            items = data.get('data', {}).get('list', [])
            if not items:
                break
            for p in items:
                profiles.append({
                    'user_id': p['user_id'],
                    'remark': p.get('remark', ''),
                    'proxy': p.get('user_proxy_config', {}).get('proxy_host', ''),
                })
            if len(items) < 100:
                break
            page += 1
        except Exception as e:
            print(f'{C_YELLOW}Ошибка AdsPower API: {e}{C_RESET}')
            break
    return profiles[:count]


def start_browser(user_id):
    resp = requests.get(f'{ADS_API}/api/v1/browser/start', params={
        'user_id': user_id,
    }, timeout=30)
    data = resp.json()
    if data.get('code') != 0:
        return None, data.get('msg', 'Unknown error')
    return data.get('data'), None


def stop_browser(user_id):
    try:
        requests.get(f'{ADS_API}/api/v1/browser/stop', params={'user_id': user_id}, timeout=10)
    except Exception:
        pass


def process_account(email, old_password, new_password, profile, idx):
    global success_count, fail_count, skip_count, checked_count

    user_id = profile['user_id']

    if not args.skip_check:
        if not check_imap(email, old_password):
            with valid_lock:
                checked_count += 1
                skip_count += 1
                print(f'  [{checked_count}/{total}] {C_YELLOW}SKIP{C_RESET}  {email} (невалидный)')
            return (idx, email, old_password, new_password, False, 'IMAP невалидный')

    try:
        browser_data, err = start_browser(user_id)
        if not browser_data:
            with valid_lock:
                checked_count += 1
                fail_count += 1
                print(f'  [{checked_count}/{total}] {C_RED}ERR{C_RESET}   {email} ({err})')
            return (idx, email, old_password, new_password, False, f'Browser: {err}')

        ws = browser_data.get('ws', {}).get('puppeteer')
        if not ws:
            stop_browser(user_id)
            with valid_lock:
                checked_count += 1
                fail_count += 1
                print(f'  [{checked_count}/{total}] {C_RED}ERR{C_RESET}   {email} (нет ws)')
            return (idx, email, old_password, new_password, False, 'No WS endpoint')

        result = do_change(ws, email, old_password, new_password)
        stop_browser(user_id)

        with valid_lock:
            checked_count += 1
            if result[0]:
                success_count += 1
                print(f'  [{checked_count}/{total}] {C_GREEN}OK{C_RESET}    {email} -> {new_password[:12]}...')
            else:
                fail_count += 1
                print(f'  [{checked_count}/{total}] {C_RED}FAIL{C_RESET}  {email} ({result[1][:60]})')
                with open('errors.txt', 'a', encoding='utf-8') as f:
                    f.write(f'{email}:{old_password} | {result[1]}\n')

        return (idx, email, old_password, new_password, result[0], result[1])

    except Exception as e:
        stop_browser(user_id)
        with valid_lock:
            checked_count += 1
            fail_count += 1
            print(f'  [{checked_count}/{total}] {C_RED}ERR{C_RESET}   {email} ({str(e)[:60]})')
        return (idx, email, old_password, new_password, False, str(e))


def do_change(ws, email, old_password, new_password):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        page.goto('https://mail.rambler.ru/', timeout=TIMEOUT * 1000)
        page.wait_for_load_state('networkidle', timeout=TIMEOUT * 1000)
        time.sleep(2)

        login_input = page.query_selector('input[type="text"]')
        pass_input = page.query_selector('input[type="password"]')

        if not login_input or not pass_input:
            return False, 'Не найдены поля ввода'

        login_input.fill(email)
        time.sleep(0.3)
        pass_input.fill(old_password)
        time.sleep(0.3)

        submit = None
        for b in page.query_selector_all('button'):
            if 'войти' in (b.text_content() or '').lower():
                submit = b
                break

        if not submit:
            return False, 'Нет кнопки Войти'

        submit.click()
        time.sleep(5)
        page.wait_for_load_state('networkidle', timeout=TIMEOUT * 1000)

        if '/auth' in page.url:
            hcaptcha = page.query_selector('iframe[src*="hcaptcha"]')
            if hcaptcha:
                print(f'\n  {C_YELLOW}!!! КАПTCHA: {email} — реши в браузере и нажми Enter{C_RESET}')
                input('  > ')
                time.sleep(3)
                page.wait_for_load_state('networkidle', timeout=TIMEOUT * 1000)
            if '/auth' in page.url:
                return False, 'Не удалось войти'

        time.sleep(2)

        page.goto('https://mail.rambler.ru/#/settings/security/', timeout=TIMEOUT * 1000)
        page.wait_for_load_state('networkidle', timeout=TIMEOUT * 1000)
        time.sleep(3)

        btn = page.query_selector('button:has-text("Изменить пароль")') or \
              page.query_selector('button:has-text("Сменить")') or \
              page.query_selector('a:has-text("Изменить пароль")')
        if btn:
            btn.click()
            time.sleep(2)

        inputs = page.query_selector_all('input[type="password"]')
        if len(inputs) >= 3:
            inputs[0].fill(old_password)
            time.sleep(0.2)
            inputs[1].fill(new_password)
            time.sleep(0.2)
            inputs[2].fill(new_password)
            time.sleep(0.5)
        elif len(inputs) >= 2:
            inputs[0].fill(old_password)
            time.sleep(0.2)
            inputs[1].fill(new_password)
            time.sleep(0.5)
        else:
            return False, f'Полей пароля: {len(inputs)}'

        save = page.query_selector('button[type="submit"]') or \
               page.query_selector('button:has-text("Сохранить")') or \
               page.query_selector('button:has-text("Подтвердить")')
        if save:
            save.click()
            time.sleep(3)
            page.wait_for_load_state('networkidle', timeout=TIMEOUT * 1000)
            return True, 'OK'

        return False, 'Нет кнопки Сохранить'


def main():
    global total

    accounts = load_accounts()
    change_count = args.change if args.change > 0 else len(accounts)
    change_count = min(change_count, len(accounts))
    accounts = accounts[:change_count]
    total = change_count

    print(f'\n{C_CYAN}=== Rambler Pass Changer ==={C_RESET}')
    print(f'Почт: {total} | Потоков: {THREADS}\n')

    print(f'{C_CYAN}Загрузка профилей AdsPower...{C_RESET}')
    profiles = get_adspower_profiles(total)
    print(f'Профилей: {len(profiles)}')

    if len(profiles) < total:
        print(f'{C_YELLOW}Профилей меньше чем почт! Будет обработано: {len(profiles)}{C_RESET}')
        total = len(profiles)
        accounts = accounts[:total]

    existing = set(acc[1] for acc in accounts)
    new_passwords = generate_unique_passwords(total, existing)

    if args.dry_run:
        print(f'\n{C_YELLOW}--- dry-run ---{C_RESET}\n')
        with open('old_logins.txt', 'w', encoding='utf-8') as f:
            for email, pwd in accounts:
                f.write(f'{email}:{pwd}\n')
        with open('new_logins.txt', 'w', encoding='utf-8') as f:
            for i, (email, _) in enumerate(accounts):
                f.write(f'{email}:{new_passwords[i]}\n')
        print(f'{C_GREEN}Созданы: old_logins.txt, new_logins.txt{C_RESET}\n')
        for i in range(total):
            print(f'  {accounts[i][0]}')
            print(f'    {C_YELLOW}старый:{C_RESET} {accounts[i][1]}')
            print(f'    {C_GREEN}новый: {C_RESET} {new_passwords[i]}')
            print(f'    {C_CYAN}профиль:{C_RESET} {profiles[i]["user_id"]} ({profiles[i]["proxy"]})')
            print()
        return

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {
            executor.submit(process_account, email, pwd, new_passwords[i], profiles[i], i): email
            for i, (email, pwd) in enumerate(accounts)
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda x: x[0])

    if results:
        with open('old_logins.txt', 'w', encoding='utf-8') as f:
            for _, email, pwd, _, _, _ in results:
                f.write(f'{email}:{pwd}\n')
        with open('new_logins.txt', 'w', encoding='utf-8') as f:
            for _, email, _, new_pwd, ok, _ in results:
                if ok:
                    f.write(f'{email}:{new_pwd}\n')

    elapsed = time.time() - start_time

    print(f'\n{C_CYAN}=== РЕЗУЛЬТАТ ==={C_RESET}')
    print(f'Всего:       {total}')
    print(f'{C_GREEN}Успешно:     {success_count}{C_RESET}')
    print(f'{C_RED}Неудачно:    {fail_count}{C_RESET}')
    print(f'{C_YELLOW}Пропущено:   {skip_count}{C_RESET}')
    print(f'Время:       {elapsed:.1f} сек')

    if success_count > 0:
        print(f'\n{C_GREEN}old_logins.txt + new_logins.txt{C_RESET}')
    if fail_count > 0:
        print(f'{C_YELLOW}errors.txt{C_RESET}')
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n{C_YELLOW}Прервано{C_RESET}')
    except Exception as e:
        print(f'{C_RED}Ошибка: {e}{C_RESET}')
    finally:
        if not args.dry_run and sys.stdin.isatty():
            input('\nEnter, чтобы выйти...')
