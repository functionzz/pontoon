from django.urls import path

from pontoon.insights.views import edit_locales, insights


urlpatterns = [
    # Insights page
    path(
        "insights/",
        insights,
        name="pontoon.insights",
    ),
    # Insights config page
    path(
        "ajax/user/selector/",
        edit_locales,
        name="pontoon.insights.edit_locale_selector",
    ),
]
