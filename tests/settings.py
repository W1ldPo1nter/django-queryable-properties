# encoding: utf-8

from django import VERSION as DJANGO_VERSION

SECRET_KEY = '1337' * 8

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'queryable_properties.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}


INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',
    'queryable_properties',
    'tests.app_management',
)
if DJANGO_VERSION < (1, 9):
    INSTALLED_APPS += ('tests.dummy_lib',)  # Django versions before 1.9 don't support abstract models outside of apps

SITE_ID = 1
