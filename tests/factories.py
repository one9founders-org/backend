import factory
from factory.django import DjangoModelFactory
from faker import Faker

from api.models import Category, Deal, News, NewsletterSubscription, Review, Tool

fake = Faker()


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Faker("word")
    slug = factory.LazyAttribute(lambda obj: obj.name.lower())
    description = factory.Faker("sentence")


class ToolFactory(DjangoModelFactory):
    class Meta:
        model = Tool

    name = factory.Faker("company")
    slug = factory.LazyAttribute(
        lambda obj: obj.name.lower().replace(" ", "-").replace(",", "")
    )
    description = factory.Faker("text", max_nb_chars=200)
    website = factory.Faker("url")
    pricing_models = factory.LazyFunction(lambda: ["free"])
    tags = factory.LazyFunction(lambda: ["productivity"])  # Prevent AI enrichment
    is_featured = False
    is_active = True

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        if not create:
            return

        # Always ensure at least one category exists
        if extracted:
            for category in extracted:
                self.categories.add(category)
        else:
            # Create a new category and add it
            category = CategoryFactory()
            self.categories.add(category)

        # Save after adding categories
        self.save()


class ReviewFactory(DjangoModelFactory):
    class Meta:
        model = Review

    tool = factory.SubFactory(ToolFactory)
    user_name = factory.Faker("name")
    rating = factory.Faker("random_int", min=1, max=5)
    title = factory.Faker("sentence", nb_words=4)
    comment = factory.Faker("text", max_nb_chars=300)


class DealFactory(DjangoModelFactory):
    class Meta:
        model = Deal

    tool = factory.SubFactory(ToolFactory)
    title = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("text", max_nb_chars=200)
    discount_percentage = factory.Faker("random_int", min=10, max=90)
    deal_url = factory.Faker("url")
    is_active = True


class NewsFactory(DjangoModelFactory):
    class Meta:
        model = News

    title = factory.Faker("sentence", nb_words=8)
    content = factory.Faker("text", max_nb_chars=500)
    author = factory.Faker("name")
    is_published = True


class NewsletterSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = NewsletterSubscription

    email = factory.Faker("email")
    source = factory.Faker("random_element", elements=["homepage", "blog", "tool_page"])
    is_active = True
