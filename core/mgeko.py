import re
import json
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from config import MGEKO_BASE, SEARCH_URL
from paths import get_data_dir
from storage import load_settings
from models import Manga, Chapter


class MgekoError(Exception):
    pass


class MgekoClient:
    def __init__(self, log=None):
        self.log = log or (lambda _: None)
        self.settings = load_settings()

        self.pw = None
        self.browser = None
        self.context = None
        self.page = None

    # ==========================================================
    # BROWSER
    # ==========================================================

    def start(self):
        self.settings = load_settings()

        headless = bool(self.settings.get("headless", True))
        browser_name = str(self.settings.get("browser", "firefox")).lower().strip()
        nav_timeout = int(self.settings.get("navigation_timeout", 45000))

        self.log("Запускаю браузер...")

        self.pw = sync_playwright().start()

        if browser_name == "firefox":
            self.log("Браузер: Firefox")
            self.browser = self.pw.firefox.launch(headless=headless)
        else:
            self.log("Браузер: Chromium")
            self.browser = self.pw.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )

        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) "
                "Gecko/20100101 Firefox/131.0"
            ),
            locale="en-US",
            timezone_id="America/Toronto",
        )
        self.context.set_default_timeout(nav_timeout)

        self.page = self.context.new_page()

        self.page.on(
            "console",
            lambda message: self.log(f"[JS] {message.type}: {message.text}"),
        )
        self.page.on(
            "pageerror",
            lambda error: self.log(f"[PAGE ERROR] {error}"),
        )
        self.page.on(
            "requestfailed",
            lambda request: self.log(
                f"[REQUEST FAILED] {request.method} {request.url} -> {request.failure}"
            ),
        )
        self.page.on("response", self._on_response)

        self.log("Браузер запущен.")

    def _on_response(self, response):
        url = response.url
        if "mgeko.cc" in url and response.status >= 400:
            self.log(f"[HTTP {response.status}] {url}")

    # ==========================================================
    # CLOSE
    # ==========================================================

    def close(self):
        try:
            if self.context:
                self.context.close()
        except Exception as exc:
            self.log(f"Ошибка закрытия context: {exc}")
        try:
            if self.browser:
                self.browser.close()
        except Exception as exc:
            self.log(f"Ошибка закрытия browser: {exc}")
        try:
            if self.pw:
                self.pw.stop()
        except Exception as exc:
            self.log(f"Ошибка остановки Playwright: {exc}")

        self.page = None
        self.context = None
        self.browser = None
        self.pw = None

    # ==========================================================
    # NAVIGATION
    # ==========================================================

    def _goto(self, url, wait_for=None, timeout_selector=8000):
        if not self.page:
            raise MgekoError("Браузер не запущен.")

        nav_timeout = int(self.settings.get("navigation_timeout", 45000))

        self.log("")
        self.log("=" * 70)
        self.log("Открываю страницу:")
        self.log(url)
        self.log("=" * 70)

        try:
            response = self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=nav_timeout,
            )
            if response:
                self.log(f"HTTP статус: {response.status}")
                self.log(f"Финальный URL: {self.page.url}")
        except Exception as exc:
            self.log(f"Ошибка перехода на страницу: {exc}")
            self._save_debug_page("navigation_error")
            raise

        if wait_for:
            try:
                self.page.wait_for_selector(
                    wait_for,
                    timeout=timeout_selector,
                    state="attached",
                )
                self.log(f"Селектор найден: {wait_for}")
            except Exception:
                self.log(f"Селектор не появился за {timeout_selector}ms: {wait_for}")

        try:
            self.page.wait_for_timeout(700)
        except Exception:
            pass

        self.log(f"Текущий URL: {self.page.url}")
        self.log(f"Заголовок страницы: {self.page.title()}")

    # ==========================================================
    # DEBUG
    # ==========================================================

    def _save_debug_page(self, name):
        if not self.page:
            return
        try:
            debug_dir = get_data_dir() / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name)
            html_path = debug_dir / f"{safe_name}.html"
            html_path.write_text(self.page.content(), encoding="utf-8")
            self.log(f"DEBUG HTML сохранён: {html_path}")
        except Exception as exc:
            self.log(f"Не удалось сохранить DEBUG HTML: {exc}")

    def save_debug_screenshot(self, name):
        if not self.page:
            return

        import os

        if not os.environ.get("PLANA_DP_DEBUG"):
            return

        try:
            debug_dir = get_data_dir() / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name)
            screenshot_path = debug_dir / f"{safe_name}.png"

            self.page.screenshot(
                path=str(screenshot_path),
                full_page=False,
                timeout=8000,
            )
            self.log(f"DEBUG screenshot сохранён: {screenshot_path}")
        except Exception as exc:
            self.log(f"Не удалось сделать screenshot: {exc}")

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _clean(text):
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _title_from_url(url):
        slug = url.rstrip("/").split("/")[-1]
        return re.sub(r"[-_]+", " ", slug).title()

    @staticmethod
    def _slugify(text):
        text = (text or "").lower().strip()
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        text = re.sub(r"\s+", "-", text)
        text = re.sub(r"-+", "-", text)
        return text.strip("-")

    @staticmethod
    def _normalize_manga_url(href):
        if not href:
            return None
        absolute = urljoin(MGEKO_BASE, href.strip())
        parsed = urlparse(absolute)
        if "mgeko.cc" not in parsed.netloc.lower():
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2 or parts[0] != "manga":
            return None
        slug = parts[1].strip()
        if not slug or slug.lower() in {
            "all-chapters",
            "page",
            "list",
            "latest",
            "hot",
        }:
            return None
        return f"{MGEKO_BASE}/manga/{slug}/"

    @staticmethod
    def _extract_cover(soup):
        selectors = [
            ".novel-cover img",
            ".novel-info .novel-cover img",
            ".summary_image img",
            ".novel-info img",
            ".manga-cover img",
            ".cover img",
            "figure.novel-cover img",
            "meta[property='og:image']",
            "meta[name='twitter:image']",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                src = node.get("content", "") or ""
            else:
                src = (
                    node.get("data-src")
                    or node.get("data-lazy-src")
                    or node.get("data-original")
                    or node.get("src")
                    or ""
                )
            src = (src or "").strip()
            if not src:
                continue
            low = src.lower()
            if "placeholder" in low or "logo_" in low or "/static/img/logo" in low:
                continue
            if low.endswith(".svg"):
                continue
            return urljoin(MGEKO_BASE, src)
        return ""

    # ==========================================================
    # AUTOCOMPLETE
    # ==========================================================

    def search_via_autocomplete(self, query):
        query = self._clean(query)
        if not query:
            return []
        url = f"{MGEKO_BASE}/autocomplete?term={quote(query)}"
        self.log(f"Autocomplete запрос: {url}")
        try:
            response = self.context.request.get(
                url,
                headers={
                    "Referer": f"{MGEKO_BASE}/",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=int(self.settings.get("navigation_timeout", 45000)),
            )
        except Exception as exc:
            self.log(f"Autocomplete ошибка запроса: {exc}")
            return []
        if not response.ok:
            self.log(f"Autocomplete HTTP {response.status}")
            return []
        raw = response.text() or ""
        if not raw.strip():
            return []
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            match = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
            if match:
                try:
                    data = json.loads(match.group(1))
                except Exception:
                    data = None
        if data is None:
            return []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("results", "suggestions", "data", "items"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
        results = []
        seen = set()
        for item in items:
            title = ""
            item_url = ""
            if isinstance(item, dict):
                title = (
                    item.get("label")
                    or item.get("title")
                    or item.get("value")
                    or item.get("name")
                    or ""
                )
                item_url = item.get("url") or item.get("link") or item.get("href") or ""
            elif isinstance(item, str):
                title = item
            title = self._clean(title)
            if not item_url and title:
                item_url = f"{MGEKO_BASE}/manga/{self._slugify(title)}/"
            normalized = self._normalize_manga_url(item_url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if not title:
                title = self._title_from_url(normalized)
            results.append({"title": title, "url": normalized, "cover_url": ""})
        self.log(f"Autocomplete вернул: {len(results)}")
        return results

    # ==========================================================
    # SEARCH
    # ==========================================================

    def _extract_title_from_link(self, a):
        h4 = a.select_one("h4.novel-title, h4")
        if h4:
            text = self._clean(h4.get_text(" ", strip=True))
            if text:
                return text
        text = self._clean(a.get("title", ""))
        if text:
            return text
        img = a.select_one("img[alt]")
        if img:
            text = self._clean(img.get("alt", ""))
            if text:
                return text
        return self._clean(a.get_text(" ", strip=True))

    def _collect_candidates_from_html(self, soup):
        candidates = {}
        for li in soup.select("li.novel-item"):
            a = li.select_one("a[href]")
            if not a:
                continue
            normalized = self._normalize_manga_url(a.get("href", ""))
            if not normalized:
                continue
            title = self._extract_title_from_link(a) or self._title_from_url(normalized)
            cover_url = self._extract_cover(li)
            candidates[normalized] = {
                "title": title,
                "url": normalized,
                "cover_url": cover_url,
            }
        if not candidates:
            for a in soup.select("a[href]"):
                normalized = self._normalize_manga_url(a.get("href", ""))
                if not normalized or normalized in candidates:
                    continue
                text = self._extract_title_from_link(a) or self._title_from_url(
                    normalized
                )
                candidates[normalized] = {
                    "title": text,
                    "url": normalized,
                    "cover_url": "",
                }
        return candidates

    def _score_candidates(self, candidates_list, query):
        query_lower = query.lower()
        words = [w for w in re.split(r"\s+", query_lower) if w]
        slug_query = self._slugify(query)
        scored = []
        for item in candidates_list:
            title_lower = (item["title"] or "").lower()
            url_lower = item["url"].lower()
            score = 0
            if title_lower == query_lower:
                score += 1000
            elif query_lower in title_lower:
                score += 500
            elif title_lower and title_lower in query_lower:
                score += 200
            if slug_query and slug_query in url_lower:
                score += 300
            for word in words:
                if word in title_lower:
                    score += 50
                if word in url_lower:
                    score += 20
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda v: (-v[0], v[1]["title"].lower()))
        return [item for _, item in scored]

    def _search_on_page(self, url):
        self._goto(
            url,
            wait_for="li.novel-item a[href*='/manga/'], .novel-list a[href*='/manga/']",
            timeout_selector=8000,
        )
        html = self.page.content()
        soup = BeautifulSoup(html, "html.parser")
        html_title = self._clean(soup.title.get_text() if soup.title else "")
        self.log(f"HTML title: {html_title}")
        self.log(f"HTML размер: {len(html):,} символов")
        candidates_list = list(self._collect_candidates_from_html(soup).values())
        self.log(f"Из HTML найдено уникальных /manga/: {len(candidates_list)}")
        return candidates_list

    def search(self, query):
        query = self._clean(query)
        if not query:
            return []
        encoded = quote(query)
        url = f"{SEARCH_URL}?search={encoded}&inputContent={encoded}"
        self.log("")
        self.log(f"Поиск: {query}")
        self.log(f"URL поиска: {url}")
        candidates_list = []
        try:
            candidates_list = self._search_on_page(url)
        except Exception as exc:
            self.log(f"Ошибка при поиске: {exc}")
        self._save_debug_page("search_page")
        self.save_debug_screenshot("search_page")
        if not candidates_list:
            self.log("HTML не дал результатов. Пробую /autocomplete...")
            ac_results = self.search_via_autocomplete(query)
            if ac_results:
                candidates_list = ac_results
        if not candidates_list:
            self.log("Autocomplete тоже пуст. Пробую slug-эвристику...")
            slug_url = f"{MGEKO_BASE}/manga/{self._slugify(query)}/"
            try:
                response = self.context.request.get(
                    slug_url,
                    headers={"Referer": MGEKO_BASE},
                    timeout=int(self.settings.get("navigation_timeout", 45000)),
                )
                if response.ok and "/manga/" in response.url:
                    normalized = self._normalize_manga_url(response.url)
                    if normalized:
                        candidates_list = [
                            {
                                "title": self._title_from_url(normalized),
                                "url": normalized,
                                "cover_url": "",
                            }
                        ]
                        self.log(f"Slug-эвристика нашла: {normalized}")
                else:
                    self.log(f"Slug-эвристика: HTTP {response.status} для {slug_url}")
            except Exception as exc:
                self.log(f"Slug-эвристика ошибка: {exc}")
        for i, item in enumerate(candidates_list[:50], start=1):
            self.log(f"  {i:02d}. {item['title']} -> {item['url']}")
        results = self._score_candidates(candidates_list, query)
        if not results:
            self.log("Нет релевантных совпадений. Возвращаю всё, что нашлось.")
            results = candidates_list
        results = results[:30]
        self.log("")
        self.log(f"ИТОГОВЫХ РЕЗУЛЬТАТОВ: {len(results)}")
        for i, item in enumerate(results, start=1):
            self.log(f"[RESULT {i}] {item['title']} -> {item['url']}")
        return results

    # ==========================================================
    # PREVIEW
    # ==========================================================

    def get_manga_preview(self, url):
        try:
            response = self.context.request.get(
                url,
                headers={"Referer": MGEKO_BASE},
                timeout=int(self.settings.get("navigation_timeout", 45000)),
            )
            if not response.ok:
                self.log(f"Превью {url}: HTTP {response.status}")
                return None
            html = response.text()
        except Exception as exc:
            self.log(f"Ошибка превью {url}: {exc}")
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = self._text_first(
            soup,
            [".novel-title", "h1.novel-title", "h1", "meta[property='og:title']"],
        ) or self._title_from_url(url)
        cover = self._extract_cover(soup)
        status = self._extract_status(soup)
        genres = []
        for a in soup.select("a[href*='genre'], a[href*='genres']"):
            text = self._clean(a.get_text(" ", strip=True))
            if text and text not in genres:
                genres.append(text)
        chapters_count = len(soup.select(".chapter-list-item"))
        return {
            "title": title,
            "url": url,
            "cover_url": cover,
            "status": status,
            "genres": genres,
            "chapters_count": chapters_count,
        }

    def search_with_previews(self, query, limit=12):
        results = self.search(query)
        enriched = []
        for i, item in enumerate(results):
            if i >= limit:
                enriched.append(item)
                continue
            preview = self.get_manga_preview(item["url"])
            if preview:
                if not preview.get("title"):
                    preview["title"] = item["title"]
                if not preview.get("cover_url") and item.get("cover_url"):
                    preview["cover_url"] = item["cover_url"]
                enriched.append(preview)
            else:
                enriched.append(item)
        return enriched

    # ==========================================================
    # MANGA
    # ==========================================================

    def get_manga(self, url):
        self._goto(
            url,
            wait_for=".chapter-list-item, .novel-title",
            timeout_selector=8000,
        )
        self._save_debug_page("manga_page")
        self.save_debug_screenshot("manga_page")
        soup = BeautifulSoup(self.page.content(), "html.parser")
        title = self._text_first(
            soup,
            [".novel-title", "h1.novel-title", "h1", "meta[property='og:title']"],
        ) or self._title_from_url(url)
        alternative = self._text_first(soup, [".alternative-title"])
        author = self._extract_author(soup)
        status = self._extract_status(soup)
        description = self._text_first(
            soup,
            [".description", ".summary", ".novel-info .intro", ".intro"],
        )
        cover = self._extract_cover(soup)
        self.log(f"Cover URL: {cover or '(не найдено)'}")
        views = self._extract_stat(soup, ["views", "view"])
        bookmarks = self._extract_stat(soup, ["bookmarked", "bookmark"])
        genres = []
        for a in soup.select("a[href*='genre'], a[href*='genres']"):
            text = self._clean(a.get_text(" ", strip=True))
            if text and text not in genres:
                genres.append(text)
        chapters = self._parse_chapters(soup)
        self.log(f"Название: {title}")
        self.log(f"Автор: {author}")
        self.log(f"Статус: {status}")
        self.log(f"Глав найдено: {len(chapters)}")
        all_link = soup.select_one("#library-push[href]")
        if all_link:
            all_url = urljoin(MGEKO_BASE, all_link.get("href", ""))
            if "/all-chapters/" in all_url:
                try:
                    self.log("Открываю полный список глав:")
                    self.log(all_url)
                    self._goto(all_url, wait_for=".chapter-list-item")
                    all_soup = BeautifulSoup(self.page.content(), "html.parser")
                    all_chapters = self._parse_chapters(all_soup)
                    self.log(f"В полном списке найдено: {len(all_chapters)}")
                    chapters = self._merge_chapters(chapters, all_chapters)
                except Exception as exc:
                    self.log("Не удалось загрузить полный список глав: " + str(exc))
        return Manga(
            title=title,
            url=url,
            alternative_title=alternative,
            author=author,
            status=status,
            description=description,
            cover_url=cover,
            views=views,
            bookmarks=bookmarks,
            genres=genres,
            chapters=chapters,
        )

    # ==========================================================
    # CHAPTER PARSER
    # ==========================================================

    @staticmethod
    def _extract_chapter_number_from_url(href):
        match = re.search(r"chapter[-_/](\d+(?:[.,]\d+)?)", href, re.IGNORECASE)
        if match:
            return match.group(1).replace(",", ".")
        return ""

    def _parse_chapters(self, soup):
        chapters = []
        seen = set()
        nodes = soup.select(".chapter-list-item")
        self.log(f"Элементов .chapter-list-item: {len(nodes)}")
        for node in nodes:
            a = node.select_one("a[href]")
            if not a:
                continue
            href = a.get("href", "")
            if not href or "/reader/" not in href:
                continue
            chapter_url = urljoin(MGEKO_BASE, href)
            key = chapter_url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            number = self._extract_chapter_number_from_url(href)
            if not number:
                number = node.get("data-chapterno", "").strip()
            if not number:
                label_node = node.select_one(".chapter-number")
                if label_node:
                    label_text = self._clean(label_node.get_text(" ", strip=True))
                    m = re.search(r"(\d+(?:[.,]\d+)?)", label_text)
                    if m:
                        number = m.group(1).replace(",", ".")
            if not number:
                number = "?"
            chapter_number_node = node.select_one(".chapter-number")
            if chapter_number_node:
                label = self._clean(chapter_number_node.get_text(" ", strip=True))
            else:
                label = self._clean(node.get_text(" ", strip=True))
            stats_node = node.select_one(".chapter-stats")
            updated = (
                self._clean(stats_node.get_text(" ", strip=True)) if stats_node else ""
            )
            try:
                order = float(number.replace(",", "."))
            except ValueError:
                order = 0
            chapters.append(
                Chapter(
                    number=number,
                    url=chapter_url,
                    label=label,
                    updated=updated,
                    order=order,
                )
            )
            self.log(f"Глава {number}: {chapter_url}")
        chapters.sort(key=lambda c: (c.order, c.number), reverse=True)
        return chapters

    @staticmethod
    def _merge_chapters(first, second):
        merged = {}
        for chapter in first + second:
            merged[chapter.url.rstrip("/")] = chapter
        result = list(merged.values())
        result.sort(key=lambda c: (c.order, c.number), reverse=True)
        return result

    # ==========================================================
    # CHAPTER IMAGES
    # ==========================================================

    def get_chapter_images(self, chapter_url):
        self._goto(
            chapter_url,
            wait_for="img[src*='/sv2/comic/'], img[data-src*='/sv2/comic/']",
            timeout_selector=10000,
        )
        self._save_debug_page("chapter_page")
        self.save_debug_screenshot("chapter_page")
        soup = BeautifulSoup(self.page.content(), "html.parser")
        images = []
        seen = set()
        for img in soup.select("img"):
            src = (
                img.get("data-src") or img.get("data-lazy-src") or img.get("src") or ""
            ).strip()
            if not src:
                continue
            absolute = urljoin(chapter_url, src)
            low = absolute.lower()
            if "credits-mgeko.png" in low or "/sv2/comic/" not in low:
                continue
            image_id = img.get("id", "")
            match = re.search(r"image-(\d+)$", image_id)
            numeric = int(match.group(1)) if match else 999999
            if absolute in seen:
                continue
            seen.add(absolute)
            images.append((numeric, absolute))
        images.sort(key=lambda item: item[0])
        if not images:
            self.log("Основной поиск изображений ничего не нашёл.")
            for img in soup.select(
                "img[src*='/sv2/comic/'], img[data-src*='/sv2/comic/']"
            ):
                src = (img.get("data-src") or img.get("src") or "").strip()
                if not src or "credits-mgeko.png" in src.lower():
                    continue
                absolute = urljoin(chapter_url, src)
                if absolute in seen:
                    continue
                seen.add(absolute)
                images.append((len(images) + 1, absolute))
        result = [url for _, url in images]
        self.log(f"Найдено изображений: {len(result)}")
        for index, image_url in enumerate(result, start=1):
            self.log(f"{index:03d}: {image_url}")
        return result

    # ==========================================================
    # DOWNLOAD IMAGE
    # ==========================================================

    def download_image(self, url, destination, referer):
        retries = int(self.settings.get("image_retries", 3))
        dl_timeout = int(self.settings.get("download_timeout", 60000))
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                self.log(f"Скачивание {attempt}/{retries}: {url}")
                response = self.context.request.get(
                    url,
                    headers={
                        "Referer": referer,
                        "Accept": (
                            "image/avif,image/webp,image/apng,"
                            "image/svg+xml,image/*,*/*;q=0.8"
                        ),
                    },
                    timeout=dl_timeout,
                )
                if not response.ok:
                    raise MgekoError(f"HTTP {response.status}")
                data = response.body()
                if not data:
                    raise MgekoError("Пустой ответ")
                Path(destination).write_bytes(data)
                self.log(f"Сохранено: {destination}")
                return
            except Exception as exc:
                last_error = exc
                self.log(f"Попытка {attempt}/{retries} не удалась: {exc}")
        raise MgekoError(f"Не удалось скачать {url}: {last_error}")

    # ==========================================================
    # TEXT PARSING
    # ==========================================================

    @staticmethod
    def _text_first(soup, selectors):
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                value = node.get("content", "")
            else:
                value = node.get_text(" ", strip=True)
            value = re.sub(r"\s+", " ", value or "").strip()
            if value:
                return value
        return ""

    def _extract_author(self, soup):
        author_link = soup.select_one("a[href*='/author/'], a[href*='/authors/']")
        if author_link:
            text = self._clean(author_link.get_text(" ", strip=True))
            if text and len(text) < 120:
                return text
        for sel in (
            "div.author",
            ".author-name",
            "[class*='author']",
            ".novel-info .author",
        ):
            node = soup.select_one(sel)
            if node:
                text = self._clean(node.get_text(" ", strip=True))
                if text and len(text) < 120:
                    return text
        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"\bAuthor(?:\(s\))?\s*:\s*(.+?)"
            r"(?=\s{2,}|"
            r"\s(?:Rating|Status|Views|Bookmark|Genres|"
            r"Chapter|Read|Login|Updated|Alternative)\b)",
            text,
            re.IGNORECASE,
        )
        if match:
            value = self._clean(match.group(1))
            if value and len(value) < 120:
                return value
        return ""

    def _extract_status(self, soup):
        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"\bStatus\s*:\s*"
            r"(Ongoing|Completed|Complete|On[\s-]?Going|Hiatus|Dropped)",
            text,
            re.IGNORECASE,
        )
        if match:
            return self._clean(match.group(1))
        match = re.search(
            r"\b(Ongoing|Completed|Complete|On Going)\b",
            text,
            re.IGNORECASE,
        )
        if match:
            return self._clean(match.group(1))
        return ""

    def _extract_stat(self, soup, words):
        text = soup.get_text(" ", strip=True)
        for word in words:
            match = re.search(
                rf"([\d,.]+\s*[KMB]?)\s*{word}\b",
                text,
                re.IGNORECASE,
            )
            if match:
                return self._clean(match.group(1))
        return ""
