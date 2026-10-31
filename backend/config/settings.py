"""Postavke Django projekta za prijavu stanja vodomjera.

Sve što se razlikuje između razvoja i produkcije čita se iz varijabli okoline.
"""
import hashlib
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-samo-za-razvoj-promijeniti")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "ocitanja",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "ocitanja.sigurnost.SigurnosnaZaglavlja",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "ocitanja.sigurnost.ZastitaPrijave",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "ocitanja.upravljanje.kontekst",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL kad je POSTGRES_DB postavljen (Docker / server), inače SQLite za lokalni razvoj i testove.
if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "voda"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "ocitanja.Korisnik"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "ocitanja.sigurnost.DuljaLozinkaAdministratora", "OPTIONS": {"min_length": 12}},
    # Popis od 20 000 najčešćih lozinki iz procurjelih baza.
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2 za nove lozinke; postojeće se prebacuju same kod sljedeće prijave.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Nakon ovoliko neuspjelih prijava za isto korisničko ime (ili s iste adrese) prijava je blokirana BLOKADA_MINUTA.
BLOKADA_POKUSAJA = int(os.environ.get("BLOKADA_POKUSAJA", "5"))
BLOKADA_POKUSAJA_ADRESA = int(os.environ.get("BLOKADA_POKUSAJA_ADRESA", "20"))
BLOKADA_MINUTA = int(os.environ.get("BLOKADA_MINUTA", "15"))

# Link za zaboravljenu lozinku vrijedi sat vremena; najviše toliko zahtjeva na sat za istu adresu i s iste IP adrese.
PASSWORD_RESET_TIMEOUT = int(os.environ.get("RESET_LOZINKE_SEKUNDI", "3600"))
RESET_LOZINKE_PO_ADRESI = int(os.environ.get("RESET_LOZINKE_PO_ADRESI", "3"))
RESET_LOZINKE_PO_IP = int(os.environ.get("RESET_LOZINKE_PO_IP", "10"))

# Web sesija administratora istječe nakon 30 minuta neaktivnosti.
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Prijava u Android aplikaciji istječe nakon ovoliko dana nekorištenja.
TOKEN_ISTEK_DANA = int(os.environ.get("TOKEN_ISTEK_DANA", "90"))

# Django administracija (samo superadministrator) nije na pogodivoj adresi /admin/.
ADMIN_PUTANJA = os.environ.get("DJANGO_ADMIN_PUTANJA") or (
    "sustav-" + hashlib.sha256(f"admin:{SECRET_KEY}".encode()).hexdigest()[:12] + "/"
)

LANGUAGE_CODE = "hr"
TIME_ZONE = "Europe/Zagreb"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "static"))
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "prijava"
LOGIN_REDIRECT_URL = "pregled"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "ocitanja.sigurnost.TokenSIstekom",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# Fotografije vodomjera s mobitela mogu biti nekoliko MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

# APK Android aplikacije koji server nudi suvlasnicima na /aplikacija/ (puni ga deploy/preuzmi-apk.sh).
APK_DATOTEKA = Path(os.environ.get("APK_DATOTEKA", BASE_DIR / "apk" / "ocitanje-vode.apk"))
# Broj verzije (versionCode) tog APK-a; uz njega ga sprema deploy/preuzmi-apk.sh.
APK_VERZIJA = APK_DATOTEKA.with_name("verzija.txt")

# Razlika veća od ovoliko puta prosjeka stana označava se za provjeru.
PRAG_SUMNJIVE_RAZLIKE = float(os.environ.get("PRAG_SUMNJIVE_RAZLIKE", "3"))

# E-pošta: link za zaboravljenu lozinku, podsjetnici suvlasnicima i popis neočitanih administratoru.
# Bez EMAIL_HOST poruka se samo ispisuje u log.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    # Port 465 (npr. neki hosting): EMAIL_USE_SSL=1; port 587 (Gmail, Brevo): STARTTLS.
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0") == "1"
    EMAIL_USE_TLS = not EMAIL_USE_SSL and os.environ.get("EMAIL_USE_TLS", "1") == "1"
    EMAIL_TIMEOUT = 20
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", os.environ.get("EMAIL_HOST_USER", "prijava-vode@localhost"))

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "1") == "1"
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    if SESSION_COOKIE_SECURE:
        # Preglednik nakon prvog posjeta godinu dana stranicu otvara samo preko HTTPS-a.
        SECURE_SSL_REDIRECT = True
        SECURE_HSTS_SECONDS = 365 * 24 * 3600
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
