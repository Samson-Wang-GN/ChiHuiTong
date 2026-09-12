from django.urls import include, path
from django.conf import settings

urlpatterns = [path("api/v1/", include("chihuitong.urls"))]
if settings.ACCEPTANCE_ENABLED:
    from chihuitong import acceptance

    urlpatterns += [
        path("", acceptance.index),
        path("acceptance/sms", acceptance.inbox),
        path("assets/<str:name>", acceptance.asset),
        path("<str:role>/", acceptance.index),
    ]
