GREMLIN GPLv3
=============

The open source, low-code legal engineering platform.

.. image:: https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg
     :target: https://github.com/pydanny/cookiecutter-django/
     :alt: Built with Cookiecutter Django
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
     :target: https://github.com/ambv/black
     :alt: Black code style


:License: GPLv3


Installation
------------

**The easiest way to install the Gremlin beta is via Docker-Compose. Ideally we can build some one-click installers for
1.0 release.**

- Requirements
    - Django > 3.1
    - Celery 4
    - Python > 3.6
    - Redis
    - Postgres
    - Docker
    - Docker-compose

- Optional Requirements
    - **Amazon AWS S3 Bucket** - This is optional in theory, though I've not tested the system storing files locally.
      This won't be scalable, however.
    - **SendGrid API Key** - If you want to enable password recovery, username recovery email updates and other features
      that depend on sending e-mails, you'll need a SendGrid API key.

- Install Prerequisites (Assuming Ubuntu 18.04)
    - First, setup Docker:
        - I recommend you follow Digital Ocean's excellent instructions at https://www.digitalocean.com/community/tutorials/how-to-install-and-use-docker-on-ubuntu-18-04
    - Next, setup Docker Compose:
        - Again, highly recommended you follow the Digital Ocean walkthrough here: https://www.digitalocean.com/community/tutorials/how-to-install-docker-compose-on-ubuntu-18-04

- Gremlin Installation steps
    - In your terminal, cd to the directory you'd like to run Gremlin from.
    - Clone the latest repository::

        Github link goes here

    - cd into the repository directory and create a .env folder::

        cd EXAMPLE
        sudo mkdir .env
        cd .env
        sudo mkdir .production
        cd .production

    - Create two env variables files:
        - *.django*::

            # General
            # ------------------------------------------------------------------------------
            # DJANGO_READ_DOT_ENV_FILE=True
            DJANGO_SETTINGS_MODULE=config.settings.production
            DJANGO_SECRET_KEY=<<secret key>>
            DJANGO_ADMIN_URL=<<desired admin url>>
            DJANGO_ALLOWED_HOSTS=<<deployment url>>

            # Security
            # ------------------------------------------------------------------------------
            # TIP: better off using DNS, however, redirect is OK too
            DJANGO_SECURE_SSL_REDIRECT=False

            # Email
            # ------------------------------------------------------------------------------
            DJANGO_SERVER_EMAIL=no-reply@e

            # SENDGRID
            # -------------------------------------------------------------------------------
            SENDGRID_API_KEY=<<Sendgrid API Key>>

            # AWS
            # ------------------------------------------------------------------------------
            DJANGO_AWS_ACCESS_KEY_ID=<<access key>>
            DJANGO_AWS_SECRET_ACCESS_KEY=<<secret access key>>
            DJANGO_AWS_STORAGE_BUCKET_NAME=<<bucket name>>
            DJANGO_AWS_S3_REGION_NAME=<<region>>

            # django-allauth
            # ------------------------------------------------------------------------------
            DJANGO_ACCOUNT_ALLOW_REGISTRATION=False

            # Gunicorn
            # ------------------------------------------------------------------------------
            WEB_CONCURRENCY=4

            # Redis
            # ------------------------------------------------------------------------------
            REDIS_URL=redis://redis:6379/0

            # Flower
            CELERY_FLOWER_USER=<<alphanumeric string>>
            CELERY_FLOWER_PASSWORD=<<alphanumeric string>>

            # Tika Server - For text extraction
            # -------------------------------------------------------------------------------
            TIKA_SERVER_ENDPOINT=http://tika:9998
            TIKA_CLIENT_ONLY=True

    - *.postgres*::

        # PostgreSQL
        # ------------------------------------------------------------------------------
        POSTGRES_HOST=postgres
        POSTGRES_PORT=5432
        POSTGRES_DB=gremlin_gplv3
        POSTGRES_USER=<<admin username>>
        POSTGRES_PASSWORD=<<admin password>>

- Docker-Compose Install - now, return to the main Gremlin directory and run the Docker-Compose file::

        cd ../..


Moved to settings_.

.. _settings: http://cookiecutter-django.readthedocs.io/en/latest/settings.html

Basic Commands
--------------

Setting Up Your Users
^^^^^^^^^^^^^^^^^^^^^

* To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

* To create an **superuser account**, use this command::

    $ python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

Type checks
^^^^^^^^^^^

Running type checks with mypy:

::

  $ mypy gremlin_gplv3

Test coverage
^^^^^^^^^^^^^

To run the tests, check your test coverage, and generate an HTML coverage report::

    $ coverage run -m pytest
    $ coverage html
    $ open htmlcov/index.html

Running tests with py.test
~~~~~~~~~~~~~~~~~~~~~~~~~~

::

  $ pytest

Live reloading and Sass CSS compilation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Moved to `Live reloading and SASS compilation`_.

.. _`Live reloading and SASS compilation`: http://cookiecutter-django.readthedocs.io/en/latest/live-reloading-and-sass-compilation.html



Celery
^^^^^^

This app comes with Celery.

To run a celery worker:

.. code-block:: bash

    cd gremlin_gplv3
    celery -A config.celery_app worker -l info

Please note: For Celery's import magic to work, it is important *where* the celery commands are run. If you are in the same folder with *manage.py*, you should be right.





Deployment
----------

The following details how to deploy this application.



Docker
^^^^^^

See detailed `cookiecutter-django Docker documentation`_.

.. _`cookiecutter-django Docker documentation`: http://cookiecutter-django.readthedocs.io/en/latest/deployment-with-docker.html



