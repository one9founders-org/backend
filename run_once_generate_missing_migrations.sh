#!/usr/bin/env bash
# run_once_generate_missing_migrations.sh
#
# Run this ONCE on your local machine (with the DB running) to generate
# the missing migration files for rag_directory and research_papers.
# Then commit the generated files.
#
# Usage:
#   chmod +x run_once_generate_missing_migrations.sh
#   ./run_once_generate_missing_migrations.sh

set -e

echo "Generating missing migrations..."

python manage.py makemigrations rag_directory
python manage.py makemigrations research_papers

echo ""
echo "Done. Files created in:"
echo "  rag_directory/migrations/"
echo "  research_papers/migrations/"
echo ""
echo "Now run: git add rag_directory/migrations/ research_papers/migrations/"
echo "         git commit -m 'feat: add initial migrations for rag_directory and research_papers'"
