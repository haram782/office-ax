from django.contrib import admin

from .models import RagAsset


@admin.register(RagAsset)
class RagAssetAdmin(admin.ModelAdmin):
    list_display = ["group_name", "kind", "trained", "file_size", "owner", "created_at"]
    list_filter = ["kind", "trained"]
    search_fields = ["group_name", "owner__username"]
