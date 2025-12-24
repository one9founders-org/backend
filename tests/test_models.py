import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from tests.factories import CategoryFactory, ReviewFactory, ToolFactory


@pytest.mark.django_db
class TestCategoryModel:
    def test_category_creation(self):
        category = CategoryFactory()
        assert category.name
        assert category.slug
        assert category.description

    def test_category_str_representation(self):
        category = CategoryFactory(name="AI Assistant")
        assert str(category) == "AI Assistant"

    def test_unique_slug_constraint(self):
        CategoryFactory(slug="ai-assistant")
        with pytest.raises(IntegrityError):
            CategoryFactory(slug="ai-assistant")


@pytest.mark.django_db
class TestToolModel:
    def test_tool_creation(self):
        tool = ToolFactory()
        assert tool.name
        assert tool.description
        assert tool.website
        assert tool.categories.count() > 0
        assert len(tool.pricing_models) > 0

    def test_tool_str_representation(self):
        tool = ToolFactory(name="ChatGPT")
        assert str(tool) == "ChatGPT"

    def test_tool_average_rating_no_reviews(self):
        tool = ToolFactory()
        assert tool.rating == 0.0

    def test_tool_average_rating_with_reviews(self):
        tool = ToolFactory()
        ReviewFactory(tool=tool, rating=4)
        ReviewFactory(tool=tool, rating=5)
        tool.refresh_from_db()
        assert tool.rating == 4.5

    def test_tool_review_count(self):
        tool = ToolFactory()
        ReviewFactory.create_batch(3, tool=tool)
        assert tool.review_count == 3


@pytest.mark.django_db
class TestReviewModel:
    def test_review_creation(self):
        review = ReviewFactory()
        assert review.tool
        assert review.user_name
        assert 1 <= review.rating <= 5
        assert review.title
        assert review.comment

    def test_review_str_representation(self):
        review = ReviewFactory(title="Great tool", user_name="John")
        assert str(review) == "Great tool by John"

    def test_rating_validation(self):
        with pytest.raises(ValidationError):
            review = ReviewFactory.build(rating=6)
            review.full_clean()
