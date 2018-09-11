# encoding: utf-8

# CHANGE THIS!
SECRET_KEY = '96a40240ed25433cb8ff8ce819bf710b'

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
)

ROOT_URLCONF = 'queryable_properties.urls'

SITE_ID = 1

QUERYABLE_PROPERTIES_IMPORTANT = 23
QUERYABLE_PROPERTIES_FOO = 'baz'
