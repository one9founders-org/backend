#!/bin/bash

# Test runner script for local development

echo "🧪 Running One9Founders Backend Tests"
echo "======================================"

# python -m venv venv
source venv/bin/activate
# Set test environment
export DJANGO_SETTINGS_MODULE=config.test_settings

# Setup test database with pgvector
echo "🗄️ Setting up test database..."
python manage.py migrate

# Run code formatting
echo "🎨 Formatting code with Black..."
black api/ config/ tests/

echo "📦 Sorting imports with isort..."
isort api/ config/ tests/

# Run linting checks
echo "🔍 Running code quality checks..."
flake8 api/ config/ tests/ --max-line-length=88 --exclude=migrations

# Run security checks
echo "🔒 Running security checks..."
bandit -r api/ -ll || true
safety check || true

pytest --cov=api --cov-report=html --cov-report=term-missing -v

echo "✅ All checks completed!"
echo "📊 Coverage report available in htmlcov/index.html"
