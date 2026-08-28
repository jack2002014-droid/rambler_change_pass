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
parser.add_argument('--proxy', default='', help='Прокси для создания новых профилей (socks5://user:pass@host:port)')
parser.add_argument('--create-profiles', type=int, default=0, help='Создать N новых профилей в AdsPower')
args = parser.parse_args()

THREADS = args.worker
CREDENTIALS_FILE = args.input
ADS_API = args.api
IMAP_HOST = 'imap.rambler.ru'
IMAP_PORT = 993
TIMEOUT = 45

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
    """Берём профили из AdsPower, мэтчим по email в remark если есть"""
    profiles = []
    all_profiles = []
    page = 1
    while True:
        try:
            resp = requests.get(f'{ADS_API}/api/v1/user/list', params={
                'page': page, 'page_size': 100
            }, timeout=10)
            data = resp.json()
            if data.get('code') != 0:
                break
            items = data.get('data', {}).get('list', [])
            if not items:
                break
            for p in items:
                all_profiles.append({
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

    accounts = load_accounts()
    accounts_to_process = accounts[:count]

    matched = {}
    for acc_email, _ in accounts_to_process:
        for prof in all_profiles:
            remark = prof.get('remark', '')
            if acc_email in remark:
                matched[acc_email] = prof
                break

    for acc_email, _ in accounts_to_process:
        if acc_email in matched:
            profiles.append(matched[acc_email])

    if len(profiles) < count:
        remaining = [p for p in all_profiles if p not in matched.values()]
        for p in remaining:
            if len(profiles) >= count:
                break
            profiles.append(p)

    return profiles[:count]


def create_adspower_profiles(count, proxy_str):
    """Создаём N новых профилей в AdsPower"""
    created = []
    proxy_type = 'socks5'
    proxy_host = ''
    proxy_port = ''
    proxy_user = ''
    proxy_pass = ''

    if proxy_str:
        # Парсим прокси: socks5://user:pass@host:port
        import re
        m = re.match(r'(socks[45]|http|https)://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', proxy_str)
        if m:
            proxy_type = m.group(1)
            proxy_user = m.group(2) or ''
            proxy_pass = m.group(3) or ''
            proxy_host = m.group(4)
            proxy_port = m.group(5)
        else:
            print(f'{C_YELLOW}Не удалось распарсить прокси: {proxy_str}{C_RESET}')

    for i in range(count):
        try:
            payload = {
                'name': f'Rambler_{i+1}',
                'group_id': '0',
                'serial_number': str(i + 1),
            }
            if proxy_host:
                payload['user_proxy_config'] = {
                    'proxy_type': proxy_type,
                    'proxy_host': proxy_host,
                    'proxy_port': proxy_port,
                    'proxy_user': proxy_user,
                    'proxy_pass': proxy_pass,
                }
            resp = requests.post(f'{ADS_API}/api/v1/user/create', json=payload, timeout=10)
            data = resp.json()
            if data.get('code') == 0:
                uid = data.get('data', {}).get('id', '')
                created.append({'user_id': uid, 'remark': f'Rambler_{i+1}', 'proxy': proxy_host})
                print(f'  Профиль создан: {uid}')
            else:
                print(f'  Ошибка: {data.get("msg", "unknown")}')
        except Exception as e:
            print(f'  Ошибка создания: {e}')
    return created


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

    browser_data = None
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
            with valid_lock:
                checked_count += 1
                fail_count += 1
                print(f'  [{checked_count}/{total}] {C_RED}ERR{C_RESET}   {email} (нет ws)')
            return (idx, email, old_password, new_password, False, 'No WS endpoint')

        result = do_change(ws, email, old_password, new_password)

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
        with valid_lock:
            checked_count += 1
            fail_count += 1
            print(f'  [{checked_count}/{total}] {C_RED}ERR{C_RESET}   {email} ({str(e)[:60]})')
        return (idx, email, old_password, new_password, False, str(e))
    finally:
        stop_browser(user_id)


def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f'  [{ts}] {msg}')


def get_proxy_from_profile(user_id):
    """Получаем прокси из профиля AdsPower"""
    try:
        resp = requests.get(f'{ADS_API}/api/v1/user/list', params={
            'user_id': user_id
        }, timeout=10)
        data = resp.json()
        items = data.get('data', {}).get('list', [])
        if items:
            proxy = items[0].get('user_proxy_config', {})
            ptype = proxy.get('proxy_type', '')
            phost = proxy.get('proxy_host', '')
            pport = proxy.get('proxy_port', '')
            puser = proxy.get('proxy_user', '')
            ppass = proxy.get('proxy_pass', '')
            if phost and pport:
                return {
                    'type': ptype,
                    'host': phost,
                    'port': pport,
                    'user': puser,
                    'pass': ppass,
                }
    except Exception:
        pass
    return None


def do_change(ws, email, old_password, new_password):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        log('Подключение к браузеру...')
        browser = p.chromium.connect_over_cdp(ws)
        log(f'Контекстов: {len(browser.contexts)}')

        context = browser.contexts[0] if browser.contexts else browser.new_context()

        js_path = os.path.join(os.path.dirname(__file__), 'hcaptcha_bypass.js')
        if os.path.exists(js_path):
            with open(js_path, encoding='utf-8') as f:
                js_code = f.read()
            cdp = context.new_cdp_session(context.pages[0] if context.pages else context.new_page())
            cdp.send('Page.addScriptToEvaluateOnNewDocument', {'source': js_code})
            log('Anti-detect JS инжектирован')

        page = context.new_page()
        log(f'Страниц: {len(context.pages)}, новая вкладка')

        log('Очищаю куки...')
        try:
            context.clear_cookies()
        except Exception:
            pass
        time.sleep(1)

        log('Открываю вход id.rambler.ru...')
        for nav_attempt in range(3):
            try:
                page.goto('https://id.rambler.ru/login-20/login?rname', timeout=TIMEOUT * 1000, wait_until='domcontentloaded')
                break
            except Exception as e:
                log(f'Попытка {nav_attempt+1}: {str(e)[:60]}')
                time.sleep(3)
        log(f'URL: {page.url}')
        time.sleep(4)

        log(f'Заполняю {email}...')
        login_el = page.query_selector('#login') or page.query_selector('input[type="text"]')
        pass_el = page.query_selector('#password') or page.query_selector('input[type="password"]')
        log(f'Поля: login={login_el is not None}, pass={pass_el is not None}')

        if not login_el or not pass_el:
            page.screenshot(path='debug_no_fields.png')
            return False, 'Не найдены поля ввода'

        login_el.click()
        login_el.fill('')
        login_el.type(email, delay=50)
        time.sleep(0.3)
        pass_el.click()
        pass_el.fill('')
        pass_el.type(old_password, delay=50)
        time.sleep(0.3)

        log('Ищу кнопку Войти...')
        submit = page.query_selector('button[data-cerber-id="login_form::main::login_button"]') or \
                 page.query_selector('button[type="submit"]')
        if not submit:
            for b in page.query_selector_all('button'):
                txt = (b.text_content() or '').strip().lower()
                if 'войти' in txt:
                    submit = b
                    break
        log(f'Кнопка: {submit is not None}')

        if not submit:
            page.screenshot(path='debug_no_submit.png')
            return False, 'Нет кнопки Войти'

        log('Нажимаю Войти...')
        try:
            page.evaluate('() => { let b = document.querySelector("button[data-cerber-id=\\"login_form::main::login_button\\"]"); if(b) b.click(); else { let btns = document.querySelectorAll("button"); for(let x of btns) { if(x.textContent.trim().toLowerCase().includes("войти")) { x.click(); break; }}}} ')
        except Exception:
            submit.click()

        log('Жду стабилизации URL после логина...')
        for attempt in range(30):
            time.sleep(2)
            try:
                url = page.url
            except Exception:
                time.sleep(1)
                continue

            if 'login-20/login' in url:
                try:
                    hc = page.query_selector('iframe[src*="hcaptcha"]') or \
                         page.query_selector('iframe[title*="hCaptcha"]') or \
                         page.query_selector('.h-captcha') or \
                         page.query_selector('[data-hcaptcha-widget-id]')
                    if hc:
                        log('hCaptcha блокирует вход! Решите вручную.')
                        print(f'\n  {C_YELLOW}!!! КАПTCHA: {email} — реши в браузере и нажми Enter{C_RESET}')
                        print(f'  {C_YELLOW}    (после решения скрипт нажмёт Войти повторно){C_RESET}')
                        try:
                            input('  > ')
                        except EOFError:
                            time.sleep(30)
                        time.sleep(2)
                        token = page.evaluate('() => { let t = document.querySelector("textarea[name=\\"h-captcha-response\\"]"); return t ? t.value : ""; }')
                        if not token:
                            for _ in range(60):
                                time.sleep(3)
                                token = page.evaluate('() => { let t = document.querySelector("textarea[name=\\"h-captcha-response\\"]"); return t ? t.value : ""; }')
                                if token:
                                    break
                        try:
                            submit2 = page.query_selector('button[data-cerber-id="login_form::main::login_button"]') or \
                                      page.query_selector('button[type="submit"]')
                            if submit2:
                                submit2.click()
                                log('Повторно нажал Войти...')
                        except Exception:
                            pass
                        continue
                    iframes = page.query_selector_all('iframe')
                    if iframes:
                        for i, iframe in enumerate(iframes):
                            src = iframe.get_attribute('src') or ''
                            title = iframe.get_attribute('title') or ''
                            log(f'  iframe[{i}]: src={src[:60]} title={title[:40]}')
                        page.screenshot(path='debug_iframes.png')
                    err = page.query_selector('.rc__bmhVM')
                    if err:
                        page.screenshot(path='debug_fail.png')
                        return False, 'Неверный логин или пароль'
                except Exception:
                    pass
                log(f'Всё ещё на логине: {url[:80]}')
                time.sleep(2)
                continue

            if 'error' in url or 'bad' in url:
                page.screenshot(path='debug_sso_error.png')
                return False, f'Ошибка SSO: {url[:80]}'

            log(f'URL: {url[:80]}...')
            if 'propagate' in url or 'account' in url or 'phone-link' in url or 'redirector' in url:
                log(f'URL стабилизировался: {url[:80]}')
                break

        time.sleep(3)
        log(f'Итоговый URL: {page.url}')

        try:
            wrong = page.query_selector('.rc__bmhVM')
            if wrong:
                page.screenshot(path='debug_fail.png')
                return False, 'Неверный логин или пароль'

            banned = page.query_selector('[class*="BVnAD"]')
            if banned:
                return False, 'Аккаунт заблокирован'

            if 'login-20' in page.url and 'phone-link' not in page.url:
                page.screenshot(path='debug_still_login.png')
                return False, 'Не удалось войти'
        except Exception as e:
            log(f'Проверка после логина: контекст сброшен ({str(e)[:50]}), продолжаю...')

        log('Перехожу в профиль...')
        for nav_attempt in range(3):
            try:
                page.goto('https://id.rambler.ru/account/profile', timeout=TIMEOUT * 1000, wait_until='domcontentloaded')
                break
            except Exception as e:
                log(f'Попытка {nav_attempt+1}: {str(e)[:60]}')
                time.sleep(3)
        time.sleep(5)
        log(f'URL профиля: {page.url}')

        if 'login' in page.url or 'auth' in page.url:
            page.screenshot(path='debug_redirect_login.png')
            return False, 'Перенаправлено на логин — сессия потеряна'

        log('Перехожу на страницу смены пароля...')
        for nav_attempt in range(3):
            try:
                page.goto('https://id.rambler.ru/account/change-password', timeout=TIMEOUT * 1000, wait_until='domcontentloaded')
                break
            except Exception as e:
                log(f'Попытка {nav_attempt+1}: {str(e)[:60]}')
                time.sleep(3)
        time.sleep(5)
        log(f'URL: {page.url}')
        page.screenshot(path='debug_changepw.png')

        pw_input = page.query_selector('#password')
        new_pw_input = page.query_selector('#newPassword')
        log(f'Поля: old={pw_input is not None}, new={new_pw_input is not None}')

        if not pw_input or not new_pw_input:
            inputs = page.query_selector_all('input[type="password"]')
            log(f'Всего полей пароля: {len(inputs)}')
            if len(inputs) >= 2:
                pw_input = inputs[0]
                new_pw_input = inputs[1]
            else:
                page.screenshot(path='debug_no_inputs.png')
                return False, 'Не найдены поля пароля'

        pw_input.click()
        pw_input.fill('')
        pw_input.type(old_password, delay=50)
        time.sleep(0.3)
        new_pw_input.click()
        new_pw_input.fill('')
        new_pw_input.type(new_password, delay=50)
        time.sleep(0.3)

        hcaptcha2 = page.query_selector('iframe[src*="hcaptcha"]')
        if hcaptcha2:
            log('hCaptcha на странице смены! Решите вручную.')
            print(f'\n  {C_YELLOW}!!! КАПTCHA: {email} — реши в браузере и нажми Enter{C_RESET}')
            print(f'  {C_YELLOW}    (ПОСЛЕ нажатия Enter скрипт нажмёт Сохранить){C_RESET}')
            try:
                input('  > ')
            except EOFError:
                time.sleep(30)
            time.sleep(3)

            token = page.evaluate('() => { let t = document.querySelector("textarea[name=\\"h-captcha-response\\"]"); return t ? t.value : ""; }')
            if not token:
                log('hCaptcha не решена! Жду...')
                for _ in range(60):
                    time.sleep(3)
                    token = page.evaluate('() => { let t = document.querySelector("textarea[name=\\"h-captcha-response\\"]"); return t ? t.value : ""; }')
                    if token:
                        break
                if not token:
                    return False, 'hCaptcha не решена за 3 минуты'

        log('Ищу кнопку Сохранить...')
        save = page.query_selector('button[data-cerber-id="profile::change_password::save_password_button"]') or \
               page.query_selector('button[type="submit"]') or \
               page.query_selector('button:has-text("Сохранить")')
        if not save:
            time.sleep(3)
            save = page.query_selector('button[data-cerber-id="profile::change_password::save_password_button"]') or \
                   page.query_selector('button[type="submit"]') or \
                   page.query_selector('button:has-text("Сохранить")')
        log(f'Кнопка сохранить: {save is not None}')

        if save:
            log('Кликаю Сохранить...')
            try:
                save.evaluate('el => el.click()')
            except Exception:
                save.click()
            time.sleep(5)
            log(f'URL после сохранения: {page.url}')
            page.screenshot(path='debug_after_save.png')

            success = page.query_selector('[class*="Snackbar-success"]')
            form_gone = not page.query_selector('#newPassword')
            navigated = '/auth' in page.url or 'login' in page.url or 'account' not in page.url

            if success or form_gone or navigated:
                log('Пароль сохранён!')
                return True, 'OK'

            log('Не обнаружено подтверждения сохранения')
            return False, 'Не удалось сохранить пароль'

        log('Кнопка сохранить не найдена!')
        page.screenshot(path='debug_no_save.png')
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

    # Создание новых профилей если нужно
    if args.create_profiles > 0:
        print(f'{C_CYAN}Создание {args.create_profiles} профилей AdsPower...{C_RESET}')
        created = create_adspower_profiles(args.create_profiles, args.proxy)
        print(f'Создано: {len(created)}')
        if not created:
            print(f'{C_RED}Не удалось создать профили!{C_RESET}')
            return

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

    failed_emails = set()
    changed_emails = set()
    for _, email, _, _, ok, _ in results:
        if ok:
            changed_emails.add(email)
        else:
            failed_emails.add(email)

    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    keep = [line for line in all_lines if line.strip() and line.split(':', 1)[0] not in changed_emails]
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        f.writelines(keep)
    if changed_emails:
        log(f'Удалено из {CREDENTIALS_FILE}: {len(changed_emails)} успешно сменённых')

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
            try:
                input('\nEnter, чтобы выйти...')
            except EOFError:
                pass
