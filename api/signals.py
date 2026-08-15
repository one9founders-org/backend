from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import Category, Tool
from .tool_stats import bust_tool_stats_cache

_M2M_ACTIONS = {"post_add", "post_remove", "post_clear"}


@receiver(post_save, sender=Tool)
@receiver(post_delete, sender=Tool)
@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def invalidate_tool_stats_on_tool_or_category_change(**kwargs):
    bust_tool_stats_cache()


@receiver(m2m_changed, sender=Tool.categories.through)
def invalidate_tool_stats_on_category_m2m(action, **kwargs):
    if action in _M2M_ACTIONS:
        bust_tool_stats_cache()
