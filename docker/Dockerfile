FROM python:3.11-bookworm AS server

ARG USER_ID=1000
ARG GROUP_ID=1000

ENV DEBIAN_FRONTEND=noninteractive
ENV HGPYTHON3=1

# Python environment variables
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONPATH /app

# Install required software.
RUN apt-get update \
    # Enable downloading packages over https
    && apt-get install -y apt-transport-https \
    # Add NodeSource v24.x and install nodejs
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    # Install software
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libmemcached-dev \
        nodejs \
        postgresql-client \
        postgresql-server-dev-15 \
    # Clean up what can be cleaned up.
    && apt-get autoremove -y

# Install uv (version should match the one used in Python GitHub workflows)
COPY --from=ghcr.io/astral-sh/uv:0.7.16 /uv /bin/uv

WORKDIR /app

# Install Pontoon Python requirements
COPY requirements/* /app/requirements/
RUN uv pip install --system -r requirements/default.txt -r requirements/dev.txt -r requirements/test.txt -r requirements/lint.txt

# Create the app user
RUN groupadd -r --gid=${GROUP_ID} pontoon && useradd --uid=${USER_ID} --no-log-init -r -m -g pontoon pontoon
RUN chown -R pontoon:pontoon /app
USER pontoon

# Install the server's Node.js requirements
ENV YUGLIFY_BINARY /app/node_modules/.bin/yuglify
ENV TERSER_BINARY /app/node_modules/.bin/terser
COPY --chown=pontoon:pontoon pontoon/package.json .
RUN npm install

COPY --chown=pontoon:pontoon ./docker/config/server.env .env
COPY --chown=pontoon:pontoon . /app/

RUN python manage.py collectstatic

STOPSIGNAL SIGINT
CMD ["/app/docker/server_run.sh"]
