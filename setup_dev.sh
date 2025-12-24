#!/bin/bash

# Setup script for development environment

echo "🚀 Setting up One9Founders Backend Development Environment"
echo "=========================================================="

# Upgrade pip first
echo "⬆️ Upgrading pip..."
python -m pip install --upgrade pip

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Run initial formatting
echo "🎨 Running initial code formatting..."
black api/ config/ tests/
isort api/ config/ tests/

echo "✅ Development environment setup complete!"
echo ""
echo "📝 Available commands:"
echo "  ./run_tests.sh          - Run all tests and checks"
echo "  pre-commit run --all    - Run pre-commit hooks on all files"
echo "  black api/              - Format code with Black"
echo "  isort api/              - Sort imports"
echo "  flake8 api/             - Run linting"
