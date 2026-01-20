import os
import json
import random
import argparse
import pandas as pd
from time import sleep
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager


def create_driver():
    chrome_options = Options()
    prefs = {"profile.managed_default_content_settings.images": 2}  # без картинок
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Скрываем признак автоматизации
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    driver.maximize_window()
    return driver


def parse_one(url):
    driver = create_driver()

    try:
        driver.get(url)
        WebDriverWait(driver, 12).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        sleep(random.uniform(0.8, 1.6))  # стабилизация DOM

        html = driver.page_source  # кэшируем page_source один раз
        soup = BeautifulSoup(html, 'html.parser')

        row = {'href': url}

        # Твой проверенный блок парсинга
        try:
            row['name'] = soup.find('h1', class_='orgpage-header-view__header').get_text(strip=True)
        except:
            row['name'] = 'null'

        try:
            row['adress'] = soup.find('a', class_='orgpage-header-view__address').get_text(strip=True)
        except:
            row['adress'] = 'null'

        try:
            row['phone'] = soup.find('div', class_='orgpage-phones-view__phone-number').get_text(strip=True)
        except:
            row['phone'] = 'null'

        try:
            row['rate'] = soup.find('span', class_='business-rating-badge-view__rating-text').get_text(strip=True)
        except:
            row['rate'] = 'null'

        try:
            row['rate_count'] = soup.find('div', class_='business-header-rating-view__text').get_text(strip=True)
        except:
            row['rate_count'] = 'null'

        try:
            row['site'] = soup.find('span', class_='business-urls-view__text').get_text(strip=True)
        except:
            row['site'] = 'null'

        try:
            row['average_bill'] = soup.find('span', class_='business-features-view__valued-value').get_text(strip=True)
        except:
            row['average_bill'] = 'null'

        return row

    except Exception as e:
        print(f"   × Ошибка в потоке на {url}: {type(e).__name__} — {str(e)}")
        return {'href': url, 'name': 'null', 'adress': 'null', 'phone': 'null', 'rate': 'null', 'rate_count': 'null', 'site': 'null', 'average_bill': 'null'}

    finally:
        driver.quit()


def parse_data(hrefs, type_org, max_workers=4):
    if not hrefs:
        print("Список ссылок пустой")
        return

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parse_one, url): url for url in hrefs}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                row = future.result()
                results.append(row)
                print(f"Готово {len(results)} / {len(hrefs)} | {url}")
            except Exception as e:
                print(f"Ошибка в потоке: {e}")
                results.append({'href': url, 'name': 'null', 'adress': 'null', 'phone': 'null', 'rate': 'null', 'rate_count': 'null', 'site': 'null', 'average_bill': 'null'})

    # Сохранение результатов
    if results:
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        os.makedirs('result_output', exist_ok=True)

        df = pd.DataFrame(results)
        filepath = f'result_output/{type_org}_full_{timestamp}.csv'
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"\nГотово! Сохранено {len(df)} организаций → {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Парсер детальной информации Яндекс.Карт")
    parser.add_argument("type_org", help="Тип организации (например: legal)")
    args = parser.parse_args()

    type_org = args.type_org

    # Собираем все ссылки из папки
    all_hrefs = []
    links_dir = f'links/{type_org}'
    if not os.path.exists(links_dir):
        print(f"Папка {links_dir} не найдена!")
        exit(1)

    for file in os.listdir(links_dir):
        if file.endswith('.json'):
            with open(os.path.join(links_dir, file), 'r', encoding='utf-8') as f:
                data = json.load(f)
                hrefs = data.get('links', [])
                all_hrefs.extend(hrefs)

    all_hrefs = list(dict.fromkeys(all_hrefs))  # убираем дубликаты
    print(f"Всего уникальных ссылок: {len(all_hrefs)}")

    if not all_hrefs:
        print("Ссылок нет — выход")
        exit(0)

    # Логика продолжения с места остановки (учитывая 2000 уже спаршенных)
    last_file = 'result_output/legal_intermediate_2000.csv'  # ← подставь имя твоего последнего файла (или full.csv)
    done_hrefs = set()

    if os.path.exists(last_file):
        df_done = pd.read_csv(last_file)
        done_hrefs = set(df_done['href'].astype(str).str.strip())
        print(f"Загружено уже спаршенных ссылок из {last_file}: {len(done_hrefs)}")

    # Фильтруем — парсим только оставшиеся
    hrefs = [h for h in all_hrefs if h not in done_hrefs]
    print(f"Оставшиеся для парсинга: {len(hrefs)}")

    # Запуск многопоточного парсинга
    parse_data(hrefs, type_org, max_workers=4)  # 4 потока — оптимально для старта, можно увеличить до 6–8