from django.urls import path
from . import views

app_name = 'sentiment'

urlpatterns = [
    path('tool/<str:tool_name>/', views.get_sentiment, name='get_sentiment'),
    path('tool/<str:tool_name>/summary/', views.get_sentiment_summary, name='get_sentiment_summary'),
    path('analyse/', views.analyse_tool, name='analyse_tool'),
    path('bulk/', views.run_bulk_pipeline, name='run_bulk_pipeline'),
    path('stats/', views.get_pipeline_stats, name='get_pipeline_stats'),
    path('red-flags/', views.get_red_flag_tools, name='get_red_flag_tools'),
    path('top-rated/', views.get_top_rated_tools, name='get_top_rated_tools'),
    path('pending/', views.get_pending_tools, name='get_pending_tools'),
]