from paths import get_static_dir

APP_NAME = "PLANA_DP"
APP_VERSION = "1.0.0"

GITHUB_REPO = "ada231asd/PLANA_DP"

# Показывать кнопку обновления в настройках
GITHUB_CHECK_ENABLED = True

STATIC_DIR = get_static_dir()

# GIF
GIF_DOWNLOAD = STATIC_DIR / "tendou-kei-blue-archive.gif"
GIF_LOADING = STATIC_DIR / "kei-tendou-blue-archive.gif"
GIF_EMPTY = STATIC_DIR / "kei-tendou-blue-archive.gif"
TRANSLATE_ENABLED = False
# Логотип
LOGO_JPG = STATIC_DIR / "logo.jpg"
LOGO_ICO = STATIC_DIR / "logo.ico"

MGEKO_BASE = "https://www.mgeko.cc"
MGEKO_HOME = f"{MGEKO_BASE}/"
SEARCH_URL = f"{MGEKO_BASE}/search/"
