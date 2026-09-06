import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'unsafe-development-key')
DEBUG = os.environ.get('DEBUG', '0') == '1'
ALLOWED_HOSTS = [x.strip() for x in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if x.strip()]

INSTALLED_APPS = [
    'django.contrib.admin','django.contrib.auth','django.contrib.contenttypes',
    'django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','core',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.ActiveOrganizationMiddleware','django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','core.context_processors.active_membership']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('POSTGRES_DB','toolmigo_crm'),'USER':os.environ.get('POSTGRES_USER','toolmigo'),'PASSWORD':os.environ.get('POSTGRES_PASSWORD','toolmigo'),'HOST':os.environ.get('POSTGRES_HOST','db'),'PORT':os.environ.get('POSTGRES_PORT','5432'),'CONN_MAX_AGE':60}}
CACHES={'default':{'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':os.environ.get('REDIS_URL','redis://redis:6379/0')}}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},
    {'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AUTH_USER_MODEL = 'core.User'
LANGUAGE_CODE = 'nl-nl'; TIME_ZONE = os.environ.get('TZ','Europe/Amsterdam'); USE_I18N=True; USE_TZ=True
STATIC_URL='static/'; STATIC_ROOT=BASE_DIR/'staticfiles'; STATICFILES_DIRS=[BASE_DIR/'static']
MEDIA_ROOT=BASE_DIR/'media'; MEDIA_URL='/media/'
BACKUP_ROOT=Path(os.environ.get('BACKUP_ROOT',BASE_DIR/'backups'))
STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
LOGIN_URL='login'; LOGIN_REDIRECT_URL='dashboard'; LOGOUT_REDIRECT_URL='login'
SESSION_COOKIE_HTTPONLY=True; SESSION_COOKIE_SAMESITE='Lax'; SESSION_COOKIE_AGE=28800
SESSION_EXPIRE_AT_BROWSER_CLOSE=True; CSRF_COOKIE_HTTPONLY=True; CSRF_COOKIE_SAMESITE='Lax'
SECURE_CONTENT_TYPE_NOSNIFF=True; X_FRAME_OPTIONS='DENY'; SECURE_REFERRER_POLICY='same-origin'
SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0')=='1'; CSRF_COOKIE_SECURE=SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT=os.environ.get('HTTPS_ENABLED','0')=='1'
SECURE_HSTS_SECONDS=31536000 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS=SECURE_SSL_REDIRECT; SECURE_HSTS_PRELOAD=SECURE_SSL_REDIRECT
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
APP_VERSION=os.environ.get('APP_VERSION','1.2.0-local')
AVAILABLE_VERSION=os.environ.get('AVAILABLE_VERSION',APP_VERSION)
EMAIL_BACKEND=os.environ.get('EMAIL_BACKEND','django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST=os.environ.get('EMAIL_HOST',''); EMAIL_PORT=int(os.environ.get('EMAIL_PORT','587')); EMAIL_HOST_USER=os.environ.get('EMAIL_HOST_USER',''); EMAIL_HOST_PASSWORD=os.environ.get('EMAIL_HOST_PASSWORD',''); EMAIL_USE_TLS=os.environ.get('EMAIL_USE_TLS','1')=='1'; DEFAULT_FROM_EMAIL=os.environ.get('DEFAULT_FROM_EMAIL','noreply@localhost')
