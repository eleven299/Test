from django.contrib import admin
from .models import Project, ProjectMember, ProjectEnvironment


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'owner', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'owner__username', 'description']
    filter_horizontal = ['members']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'role', 'joined_at']
    list_filter = ['role', 'joined_at']
    search_fields = ['project__name', 'user__username']


@admin.register(ProjectEnvironment)
class ProjectEnvironmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'base_url', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'project__name']
