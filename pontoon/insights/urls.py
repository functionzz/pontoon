from django.urls import path

from pontoon.insights.views import (
    edit_user_community_health_locale_selector,
    get_locale_contributors,
    insights,
)


urlpatterns = [
    # Insights page
    path(
        "insights/",
        insights,
        name="pontoon.insights",
    ),
    # AJAX
    path(
        "ajax/locale-contributors/",
        get_locale_contributors,
        name="pontoon.insights.get_locale_contributors",
    ),
    # Insights config page
    path(
        "ajax/user/selector/",
        edit_user_community_health_locale_selector,
        name="pontoon.insights.edit_locale_selector",
    ),
]
