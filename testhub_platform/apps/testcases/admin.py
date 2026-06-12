from django.contrib import admin
from .models import TestCase, TestCaseStep, TestCaseAttachment, TestCaseComment, TestCaseImportRecord


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'project', 'author', 'priority', 'status', 'test_type', 'created_at']
    list_filter = ['priority', 'status', 'test_type', 'created_at', 'project']
    search_fields = ['title', 'description', 'project__name', 'author__username']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['project', 'author', 'assignee']


@admin.register(TestCaseStep)
class TestCaseStepAdmin(admin.ModelAdmin):
    list_display = ['testcase', 'step_number', 'action', 'expected']
    search_fields = ['testcase__title', 'action', 'expected']


@admin.register(TestCaseAttachment)
class TestCaseAttachmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'testcase', 'uploaded_by', 'uploaded_at']
    search_fields = ['name', 'testcase__title']


@admin.register(TestCaseComment)
class TestCaseCommentAdmin(admin.ModelAdmin):
    list_display = ['testcase', 'author', 'content', 'created_at']
    search_fields = ['testcase__title', 'author__username', 'content']


@admin.register(TestCaseImportRecord)
class TestCaseImportRecordAdmin(admin.ModelAdmin):
    list_display = ['import_no', 'project', 'status', 'progress', 'success_count', 'failed_count', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['import_no', 'project__name']
    readonly_fields = ['created_at', 'updated_at']
