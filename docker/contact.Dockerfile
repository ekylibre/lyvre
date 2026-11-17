# Formulaire de contact de lyvre.org (site/contact) : un seul worker, la limite de débit est en mémoire.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY site/contact/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY site/contact/contact.py .
RUN useradd --uid 1000 --no-create-home contact
USER contact
EXPOSE 5000
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "--access-logfile", "-", "contact:app"]
