from django.urls import path

from pontoon.insights.views import edit_locales, insights, render_table


urlpatterns = [
    # Insights page
    path(
        "insights/",
        insights,
        name="pontoon.insights",
    ),
    # Insights config page
    path(
        "insights/ajax/edit-locales/",
        edit_locales,
        name="pontoon.insights.edit_locales",
    ),
    path(
        "insights/ajax/render-table/",
        render_table,
        name="pontoon.insights.render_table",
    ),
]
