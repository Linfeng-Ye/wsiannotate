import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name: str, default: str = '') -> list:
    value = os.environ.get(name, default)
    return [
        item.strip()
        for item in value.split(',')
        if item.strip()
    ]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or (
    'django-insecure-iqa-'
    'x9k2m!f7@p3q&w5z#r8t$v1y6u4j0h'
)

DEBUG = _env_bool('DJANGO_DEBUG', True)

ALLOWED_HOSTS = _env_list(
    'DJANGO_ALLOWED_HOSTS',
    'localhost,127.0.0.1,[::1],wsiannotate.com,www.wsiannotate.com',
)

CSRF_TRUSTED_ORIGINS = _env_list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'https://wsiannotate.com,https://www.wsiannotate.com',
)

USE_X_FORWARDED_HOST = _env_bool('DJANGO_USE_X_FORWARDED_HOST', True)
SECURE_PROXY_SSL_HEADER = (
    'HTTP_X_FORWARDED_PROTO',
    'https',
)
SESSION_COOKIE_SECURE = _env_bool(
    'DJANGO_SESSION_COOKIE_SECURE',
    not DEBUG,
)
CSRF_COOKIE_SECURE = _env_bool(
    'DJANGO_CSRF_COOKIE_SECURE',
    not DEBUG,
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'iqa',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'iqa_site.urls'

TEMPLATES = [
    {
        'BACKEND': (
            'django.template.backends.django.DjangoTemplates'
        ),
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'iqa_site.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 30},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.'
             'UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.'
             'MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.'
             'CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.'
             'NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.'
            'CompressedManifestStaticFilesStorage'
        ),
    },
}
MEDIA_URL = os.environ.get('DJANGO_MEDIA_URL', '/media/')
if not MEDIA_URL.endswith('/'):
    MEDIA_URL += '/'
MEDIA_ROOT = Path(
    os.environ.get('DJANGO_MEDIA_ROOT', BASE_DIR / 'media')
)
SERVE_MEDIA_FILES = _env_bool('DJANGO_SERVE_MEDIA_FILES', DEBUG)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'iqa:login'
LOGIN_REDIRECT_URL = 'iqa:home'
LOGOUT_REDIRECT_URL = 'iqa:login'
