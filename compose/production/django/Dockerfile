
FROM python:3.7-buster

ENV PYTHONUNBUFFERED 1

RUN apt-get update \
  # dependencies for building Python packages
  && python -m pip install -U pip \
  && pip install setuptools \
  && apt-get install -y make \
  && apt-get install -y build-essential \
  && apt-get install -y libssl-dev \
  && apt-get install -y zlib1g-dev \
  && apt-get install -y libbz2-dev \
  && apt-get install -y libreadline-dev \
  && apt-get install -y libsqlite3-dev \
  && apt-get install -y wget \
  && apt-get install -y curl \
  && apt-get install -y llvm \
  && apt-get install -y libncurses5-dev \
  && apt-get install -y libncursesw5-dev \
  && apt-get install -y xz-utils \
  && apt-get install -y tk-dev \
  && apt-get install -y python3-dev \
  && apt-get install -y python-dev \  # psycopg2 dependencies
  && apt-get install -y libpq-dev \
  # Translations dependencies
  && apt-get install -y gettext \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
RUN pip install --no-cache-dir -r /requirements/production.txt \
    && rm -rf /requirements

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

COPY ./compose/production/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker
RUN chmod +x /start-celeryworker

COPY ./compose/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat
RUN chmod +x /start-celerybeat

COPY ./compose/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower
RUN chmod +x /start-flower

WORKDIR /app

ENTRYPOINT ["/entrypoint"]
