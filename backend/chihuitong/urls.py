from django.urls import path

from . import api
from . import api_catalog as catalog

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
    path("products", catalog.product_list),
    path("products/<uuid:product_id>", catalog.product_update),
    path("organizations/<uuid:org_id>/source-brands", catalog.brand_list),
    path("files", catalog.upload),
    path("files/<uuid:asset_id>", catalog.download),
    path("organizations/<uuid:org_id>/contracts", catalog.contract_list),
    path("contract-versions/<uuid:version_id>/submit", catalog.contract_submit),
    path("contract-versions/<uuid:version_id>/review", catalog.contract_review),
    path("contract-versions/<uuid:version_id>/products", catalog.contract_products),
    path("clinics", catalog.clinic_list),
    path("clinics/<uuid:clinic_id>", catalog.clinic_detail),
    path("clinics/<uuid:clinic_id>/profile-changes", catalog.profile_changes),
    path("profile-changes/<uuid:change_id>/review", catalog.profile_review),
    path("clinics/<uuid:clinic_id>/service-status", catalog.clinic_service),
    path("clinics/<uuid:clinic_id>/confirmation-hours", catalog.clinic_hours),
    path("clinics/<uuid:clinic_id>/channel", catalog.clinic_channel),
    path("clinics/<uuid:clinic_id>/products", catalog.clinic_products),
]
