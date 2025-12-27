import csv
import json
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from api.models import Tool, Category


class Command(BaseCommand):
    help = 'Import tools from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                created_count = 0
                updated_count = 0
                error_count = 0
                
                for row in reader:
                    try:
                        # Clean and prepare data
                        name = row.get('name', '').strip()
                        if not name:
                            self.stdout.write(f"Skipping row with empty name")
                            continue
                            
                        slug = row.get('slug', '').strip() or slugify(name)
                        
                        # Parse JSON fields safely
                        def safe_json_parse(value, default=None):
                            if not value or value.strip() == '':
                                return default or []
                            try:
                                # Handle string representations of lists
                                if isinstance(value, str):
                                    # Remove extra quotes and clean up
                                    value = value.strip('"').strip("'")
                                    if value.startswith('[') and value.endswith(']'):
                                        return json.loads(value)
                                    elif value:
                                        # Split by comma if it's a simple comma-separated string
                                        return [item.strip().strip('"').strip("'") for item in value.split(',') if item.strip()]
                                return value if isinstance(value, list) else []
                            except (json.JSONDecodeError, ValueError):
                                return default or []
                        
                        # Parse decimal fields safely
                        def safe_decimal_parse(value):
                            if not value or value.strip() == '':
                                return None
                            try:
                                return Decimal(str(value).strip())
                            except (InvalidOperation, ValueError):
                                return None
                        
                        # Parse integer fields safely
                        def safe_int_parse(value, default=0):
                            if not value or value.strip() == '':
                                return default
                            try:
                                return int(float(str(value).strip()))
                            except (ValueError, TypeError):
                                return default
                        
                        # Parse boolean fields safely
                        def safe_bool_parse(value, default=False):
                            if not value:
                                return default
                            if isinstance(value, bool):
                                return value
                            value_str = str(value).strip().lower()
                            return value_str in ['true', '1', 'yes', 'on']
                        
                        # Prepare tool data
                        tool_data = {
                            'name': name,
                            'slug': slug,
                            'short_description': row.get('short_description', '').strip()[:200],
                            'description': row.get('description', '').strip(),
                            'website': row.get('website', '').strip() or None,
                            'affiliate_url': row.get('affiliate_url', '').strip() or None,
                            'logo_url': row.get('logo_url', '').strip() or None,
                            'video_demo_url': row.get('video_demo_url', '').strip() or None,
                            'pricing_models': safe_json_parse(row.get('pricing_models')),
                            'pricing_tiers': safe_json_parse(row.get('pricing_tiers')),
                            'pricing_from': safe_decimal_parse(row.get('pricing_from')),
                            'free_tier_available': safe_bool_parse(row.get('free_tier_available')),
                            'free_trial_days': safe_int_parse(row.get('free_trial_days')) or None,
                            'tags': safe_json_parse(row.get('tags')),
                            'use_cases': safe_json_parse(row.get('use_cases')),
                            'integrations': safe_json_parse(row.get('integrations')),
                            'features': safe_json_parse(row.get('features')),
                            'platforms': safe_json_parse(row.get('platforms')),
                            'startup_benefits': row.get('startup_benefits', '').strip(),
                            'ideal_for': safe_json_parse(row.get('ideal_for')),
                            'rating': safe_decimal_parse(row.get('rating')) or Decimal('0.0'),
                            'review_count': safe_int_parse(row.get('review_count')),
                            'views_count': safe_int_parse(row.get('views_count')),
                            'startup_friendly': safe_bool_parse(row.get('startup_friendly')),
                            'verified': safe_bool_parse(row.get('verified')),
                            'is_featured': safe_bool_parse(row.get('is_featured')),
                            'is_active': safe_bool_parse(row.get('is_active', True)),
                        }
                        
                        # Create or update tool
                        tool, created = Tool.objects.update_or_create(
                            slug=slug,
                            defaults=tool_data
                        )
                        
                        # Handle categories
                        categories_data = safe_json_parse(row.get('categories'))
                        if categories_data:
                            categories = []
                            for cat_name in categories_data:
                                if cat_name and cat_name.strip():
                                    category, _ = Category.objects.get_or_create(
                                        name=cat_name.strip(),
                                        defaults={'slug': slugify(cat_name.strip())}
                                    )
                                    categories.append(category)
                            tool.categories.set(categories)
                        
                        if created:
                            created_count += 1
                            self.stdout.write(f"Created: {tool.name}")
                        else:
                            updated_count += 1
                            self.stdout.write(f"Updated: {tool.name}")
                            
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error processing row {row.get('name', 'Unknown')}: {str(e)}"
                            )
                        )
                        continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Import completed: {created_count} created, {updated_count} updated, {error_count} errors"
                    )
                )

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading CSV file: {str(e)}"))