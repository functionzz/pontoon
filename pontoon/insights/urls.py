from django.urls import include, path

from pontoon.insights.views import edit_locales, insights, render_table


urlpatterns = [
    # Insights page
    path(
        "insights/",
        include(
            [
                path(
                    "",
                    insights,
                    name="pontoon.insights",
                ),
                # AJAX
                path(
                    "ajax/",
                    include(
                        [
                            path(
                                "edit-locales/",
                                edit_locales,
                                name="pontoon.insights.edit_locales",
                            ),
                            path(
                                "render-table/",
                                render_table,
                                name="pontoon.insights.render_table",
                            ),
                        ]
                    )
                ),
            ]
        )
    ),
]
