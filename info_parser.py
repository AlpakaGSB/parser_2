import os
import json
import random
import argparse
import pandas as pd
from time import sleep
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchWindowException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager


class Parser:
    def __init__(self, driver):
        self.driver = driver

    def _restart_driver(self):
        """Перезапуск браузера при ошибках"""
        try:
            self.driver.quit()
        except:
            pass
        sleep(random.uniform(3, 6))

        chrome_options = Options()
        prefs = {"profile.managed_default_content_settings.images": 2}  # без картинок
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        # Скрываем признак автоматизации
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        self.driver.maximize_window()
        self.driver.get('https://yandex.ru/maps')
        sleep(random.uniform(2.5, 4.5))

    def safe_get(self, url, retries=3):
        for attempt in range(1, retries + 1):
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                return True
            except TimeoutException:
                print(f"[Timeout] {url} | попытка {attempt}")
                sleep(3)
            except Exception as e:
                print(f"[Ошибка загрузки] {url} | {e}")
                sleep(4)
        return False

    def parse_data(self, hrefs, type_org):
        if not hrefs:
            print("Список ссылок пустой")
            return

        # Для теста можно ограничить количество
        # hrefs = hrefs[:30]  # ← раскомментируй для проверки

        self.driver.get('https://yandex.ru/maps')
        sleep(random.uniform(2, 4))
        parent_handle = self.driver.current_window_handle

        # Твой словарь из ноутбука
        keys = {
            'href': [],
            'name': [],
            'adress': [],
            'phone': [],
            'rate': [],
            'rate_count': [],
            'site': [],
            'average_bill': []
        }

        n = 1
        for url in hrefs:
            print(f"[{n}/{len(hrefs)}] Обрабатываем: {url}")

            try:
                # Открываем в новой вкладке
                self.driver.execute_script(f'window.open("{url}", "_blank");')
                sleep(random.uniform(1.5, 3.5))

                new_handles = [h for h in self.driver.window_handles if h != parent_handle]
                if not new_handles:
                    raise Exception("Не удалось открыть вкладку")

                self.driver.switch_to.window(new_handles[0])

                # Ждём загрузки
                if not self.safe_get(url, retries=2):
                    print(f"❌ Не удалось загрузить {url}")
                    for k in keys:
                        keys[k].append('null')
                    n += 1
                    self.driver.close()
                    self.driver.switch_to.window(parent_handle)
                    continue

                sleep(random.uniform(1.2, 2.8))  # стабилизация DOM

                soup = BeautifulSoup(self.driver.page_source, 'html.parser')

                # Твой проверенный блок парсинга — без изменений
                keys['href'].append(url)

                try:
                    keys['name'].append(
                        soup.find('h1', class_='orgpage-header-view__header').get_text(strip=True)
                    )
                except:
                    keys['name'].append('null')

                try:
                    keys['adress'].append(
                        soup.find('a', class_='orgpage-header-view__address').get_text(strip=True)
                    )
                except:
                    keys['adress'].append('null')

                try:
                    keys['phone'].append(
                        soup.find('div', class_='orgpage-phones-view__phone-number').get_text(strip=True)
                    )
                except:
                    keys['phone'].append('null')

                try:
                    keys['rate'].append(
                        soup.find('span', class_='business-rating-badge-view__rating-text').get_text(strip=True)
                    )
                except:
                    keys['rate'].append('null')

                try:
                    keys['rate_count'].append(
                        soup.find('div', class_='business-header-rating-view__text').get_text(strip=True)
                    )
                except:
                    keys['rate_count'].append('null')

                try:
                    keys['site'].append(
                        soup.find('span', class_='business-urls-view__text').get_text(strip=True)
                    )
                except:
                    keys['site'].append('null')

                try:
                    keys['average_bill'].append(
                        soup.find('span', class_='business-features-view__valued-value').get_text(strip=True)
                    )
                except:
                    keys['average_bill'].append('null')

                print(f"   → Успешно: {keys['name'][-1] or 'Без имени'}")

                # Закрываем вкладку
                self.driver.close()
                self.driver.switch_to.window(parent_handle)

                # Сохранение каждые 50–100 записей
                if n % 50 == 0:
                    self._save_intermediate(keys, type_org, n)
                    print("♻️ Промежуточное сохранение + перезапуск браузера")
                    self._restart_driver()
                    parent_handle = self.driver.current_window_handle

                n += 1

            except Exception as e:
                print(f"   × Ошибка на {url}: {type(e).__name__} — {str(e)}")
                try:
                    self.driver.close()
                except:
                    pass
                self.driver.switch_to.window(parent_handle)
                sleep(random.uniform(3, 6))

                if isinstance(e, (WebDriverException, NoSuchWindowException)):
                    print("   → Критическая ошибка → перезапуск браузера")
                    self._restart_driver()
                    parent_handle = self.driver.current_window_handle

        # Финальное сохранение
        self._save_final(keys, type_org)

    def _save_intermediate(self, keys, type_org, count):
        os.makedirs('result_output', exist_ok=True)
        df = pd.DataFrame(keys)
        df.to_csv(f'result_output/{type_org}_intermediate_{count}.csv', index=False, encoding='utf-8-sig')
        print(f"Промежуточный файл сохранён: {len(df)} строк")

    def _save_final(self, keys, type_org):
        if not any(keys.values()):  # если всё пустое
            print("Нет данных для сохранения")
            return

        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        os.makedirs('result_output', exist_ok=True)

        df = pd.DataFrame(keys)
        filepath = f'result_output/{type_org}_full_{timestamp}.csv'
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"\nГотово! Сохранено {len(df)} организаций → {filepath}")
        print(df.head())  # для удобства в консоли


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
    #all_hrefs = hrefs[:10]
    if not all_hrefs:
        print("Ссылок нет — выход")
        exit(0)

    # Запускаем Chrome
    chrome_options = Options()
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    parser_instance = Parser(driver)
    parser_instance.parse_data(all_hrefs, type_org)

    driver.quit()