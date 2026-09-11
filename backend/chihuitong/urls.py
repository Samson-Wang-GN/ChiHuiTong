from django.urls import path

from . import api

urlpatterns = [
    path("health", api.health),
    path("auth/code", api.send_code),
    path("auth/login", api.login),
    path("auth/logout", api.logout),
    path("auth/me", api.me),
    path("organizations", api.organization_list),
    path("organizations/<uuid:org_id>/status", api.organization_status),
    path("organizations/<uuid:org_id>/members", api.member_list),
    path("members/<uuid:member_id>", api.member_update),
]
