import os
import random
import json
import argparse
from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# твои константы
from utils.constants import districts, ACCEPT_BUTTON, type_org_mapping


class LinksCollector:
    def __init__(self,
                 driver,
                 link='https://yandex.ru/maps',
                 max_attempts_without_new=25,
                 accept_button=ACCEPT_BUTTON,
                 accept=True):
        self.driver = driver
        self.link = link
        self.accept_button = accept_button
        self.accept = accept
        self.max_attempts_without_new = max_attempts_without_new

    def _init_driver(self):
        self.driver.maximize_window()

    def _open_page(self, request):
        self.driver.get(self.link)
        sleep(random.uniform(2.0, 3.5))

        try:
            # Принимаем куки, если появляется
            if self.accept:
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH, self.accept_button))
                    ).click()
                    print("Куки приняты")
                except:
                    pass


            search_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input.input__control'))
            )
            search_input.clear()
            search_input.send_keys(request)
            sleep(random.uniform(0.6, 1.3))

            # Кнопка поиска
            search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"], button[aria-label*="Найти"]'))
            )
            search_button.click()
            sleep(random.uniform(3.0, 5.5))  # ждём загрузки результатов

            print(f"После поиска ждём появления первых результатов...")

        except Exception as e:
            print(f"Ошибка при вводе запроса или нажатии поиска: {e}")
            self.driver.save_screenshot("debug_search_error.png")

    def run(self, city, district, type_org_ru, type_org):
        self._init_driver()
        request = f"{city} {district} {type_org_ru}".strip()
        print(f"\nЗапрос: {request}")

        self._open_page(request)

        organizations_hrefs = []
        prev_count = 0
        attempts_without_new = 0

        while attempts_without_new < self.max_attempts_without_new:
            try:
                # 1. Ждём появления хотя бы одного блока-обёртки
                WebDriverWait(self.driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.search-snippet-view__body-button-wrapper"))
                )

                # 2. Получаем все такие обёртки
                wrapper_elements = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div.search-snippet-view__body-button-wrapper"
                )

                print(f"Найдено wrapper-элементов: {len(wrapper_elements)}")

                # 3. Из них достаём ссылки
                link_elements = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.link-overlay[href^='/maps/org/']"
                )

                current_batch = []

                for el in link_elements:
                    href = el.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            href = "https://yandex.ru" + href
                        current_batch.append(href)

                # дедупликация внутри батча
                current_batch = list(dict.fromkeys(current_batch))

                print(f"Ссылок в этом батче: {len(current_batch)}")

                # добавляем в общий список
                old_len = len(organizations_hrefs)
                organizations_hrefs.extend(current_batch)
                organizations_hrefs = list(dict.fromkeys(organizations_hrefs))  # глобальная дедупликация

                new_added = len(organizations_hrefs) - old_len

                print(f"Всего уникальных ссылок: {len(organizations_hrefs)}  |  новых: {new_added}")

                if new_added == 0:
                    attempts_without_new += 1
                    print(f"Новых ссылок не появилось → попытка {attempts_without_new}/{self.max_attempts_without_new}")
                else:
                    attempts_without_new = 0

                # скролл к последнему видимому wrapper-элементу
                if wrapper_elements:
                    last_wrapper = wrapper_elements[-1]
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        last_wrapper
                    )
                    sleep(random.uniform(1.4, 3.2))

            except Exception as e:
                print(f"Ошибка во время итерации: {type(e).__name__} – {str(e)}")
                attempts_without_new += 1
                sleep(2.5)

        # Сохранение
        directory = f'links/{type_org}'
        os.makedirs(directory, exist_ok=True)

        safe_request = request.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filepath = os.path.join(directory, f"{safe_request}.json")

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({'links': organizations_hrefs}, f, ensure_ascii=False, indent=2)

        print(f"\nСохранено {len(organizations_hrefs)} уникальных ссылок → {filepath}")
        self.driver.quit()


# ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сбор ссылок с Яндекс.Карт")
    parser.add_argument("type_org", help="Тип организации (например: legal)")
    args = parser.parse_args()

    type_org = args.type_org
    type_org_ru = type_org_mapping.get(type_org, "Юридические услуги")

    # Для теста оставляем один район
    test_districts = ["Южнопортовый район"]  # ← меняй здесь для теста

    for district in test_districts:
        # Настройки браузера
        chrome_options = Options()
        prefs = {"profile.managed_default_content_settings.images": 2}  # без изображений
        chrome_options.add_experimental_option("prefs", prefs)

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Очень важная строчка против детекта
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        collector = LinksCollector(driver, accept=True)
        collector.run(
            city="Москва",
            district=district,
            type_org_ru=type_org_ru,
            type_org=type_org
        )

        sleep(random.uniform(6, 12))  # хорошая пауза между районами