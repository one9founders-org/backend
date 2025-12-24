FROM python:3.11-slim
# Pulls the 3.11-slim version of Python Image from Docker

EXPOSE 8000
# tells Docker the container is expected to bind to port 8000 at runtime

ENV PYTHONDONTWRITEBYTECODE=1
# tells Python to not write bytecode to the filesystem
ENV PYTHONUNBUFFERED=1
# writes Python output directly to the terminal; useful to monitor application logs
ENV DJANGO_SETTINGS_MODULE=config.settings
# I'm setting my Django module to run from `settings.py` in my project directory
ENV DEBUG=False
ENV ALLOWED_HOSTS=*
ENV SECRET_KEY=production-secret-key-change-this

WORKDIR /app/backend
# sets the working directory for any Dockerfile commands that follow it

COPY requirements.txt .
# Copies requirements.txt to the current working directory in the container

RUN pip install --upgrade pip && pip install -r requirements.txt
# installs dependencies in requirements.txt

# Install curl for health checks
COPY . .
# copies application code to the working directory

RUN python manage.py collectstatic --noinput
# collects static files for production

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
# Command to run the Django application in our Docker container
