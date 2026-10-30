from pathlib import Path

from environs import Env

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env()

SECRET_KEY = env.str("DJANGO_SECRET_KEY")

DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

JWT_SECRET_KEY = env.str("JWT_SECRET_KEY")

ALGORITHMS = env.list("ALGORITHMS")

TG_BOT_AUTH_KEY = env.str("TG_BOT_AUTH_KEY")

YANDEX_CLOUD_BASE_URL = "https://ai.api.cloud.yandex.net/v1"

YANDEX_CLOUD_FOLDER = env.str("YANDEX_CLOUD_FOLDER")
YANDEX_CLOUD_API_KEY = env.str("YANDEX_CLOUD_API_KEY")
YANDEX_CLOUD_MODEL = env.str("YANDEX_CLOUD_MODEL")


REFRESH_TIME = 604_800

AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB
IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

MAX_SIZE = (1920, 1920)
MAX_AVATAR_SIZE = (400, 400)

MAX_AVATAR_RESOLUTION = 2048 * 2048  # ~4.1M px: Perfect for square profile pictures
MAX_IMAGE_RESOLUTION = 3840 * 2160  # ~8.3M px: Standard 4K UHD, allows high-res landscape photos

IMAGE_ALLOWED_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp")

VIDEO_ALLOWED_TYPES = ("video/mp4", "video/webm", "video/quicktime")

ALLOWED_EXTENSIONS_HUMAN = ("jpeg", "jpg", "png", "webp", "mp4", "webm", "mov")


AUTH_USER_MODEL = "users.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "translations.apps.TranslationsConfig",
    "users.apps.UsersConfig",
    "authentication.apps.AuthConfig",
    "words.apps.WordsConfig",
    "tags.apps.TagsConfig",
    "schedules.apps.SchedulesConfig",
    "django_cleanup.apps.CleanupConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "german_learning_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "german_learning_api.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("DB_NAME", default="german_db"),
        "USER": env.str("DB_USER", default="postgres"),
        "PASSWORD": env.str("DB_PASSWORD", default="postgres"),
        "HOST": env.str("DB_HOST", default="127.0.0.1"),
        "PORT": env.str("DB_PORT", default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
