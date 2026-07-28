from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import (
    Image, Study,
    MOSStimulus, PairStimulus, QCStimulus,
    MOSResponse, PairResponse, QCResponse,
    StudyAssignment,
)


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'fname')
    search_fields = ('name', 'fname')
    list_display_links = ('id', 'name')


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'mode', 'is_active',
        'sampler', 'stimulus_count', 'stimuli_link',
    )
    list_filter = ('mode', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('stimuli_link',)

    @admin.display(description='Stimuli')
    def stimuli_link(self, obj: Study) -> str:
        if obj.pk is None:
            return '—'
        if obj.mode == Study.MODE_MOS:
            url = (
                reverse('admin:iqa_mosstimulus_changelist')
                + f'?study__id__exact={obj.pk}'
            )
            label = 'Edit MOS stimuli'
        elif obj.mode == Study.MODE_QC:
            url = (
                reverse('admin:iqa_qcstimulus_changelist')
                + f'?study__id__exact={obj.pk}'
            )
            label = 'Edit QC stimuli'
        else:
            url = (
                reverse('admin:iqa_pairstimulus_changelist')
                + f'?study__id__exact={obj.pk}'
            )
            label = 'Edit pair stimuli'
        return format_html('<a href="{}">{} ({})</a>', url, label, obj.stimulus_count())


@admin.register(MOSStimulus)
class MOSStimulusAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'study', 'order', 'image', 'reference',
    )
    list_filter = ('study',)
    raw_id_fields = ('image', 'reference')


@admin.register(PairStimulus)
class PairStimulusAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'study', 'order',
        'image_a', 'image_b',
    )
    list_filter = ('study',)
    raw_id_fields = (
        'image_a', 'image_b',
        'reference_a', 'reference_b',
    )


@admin.register(QCStimulus)
class QCStimulusAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'study', 'order', 'image', 'reference',
    )
    list_filter = ('study',)
    raw_id_fields = ('image', 'reference')


@admin.register(QCResponse)
class QCResponseAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'stimulus', 'choice', 'timestamp',
    )
    list_filter = ('stimulus__study', 'user', 'choice')


@admin.register(MOSResponse)
class MOSResponseAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'stimulus', 'score',
        'timestamp',
    )
    list_filter = ('stimulus__study', 'user')


@admin.register(PairResponse)
class PairResponseAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'stimulus', 'choice',
        'display_choice', 'was_swapped',
        'timestamp',
    )
    list_filter = ('stimulus__study', 'user')


@admin.register(StudyAssignment)
class StudyAssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'study', 'user', 'stimulus_count', 'created')
    list_filter = ('study', 'user')
    raw_id_fields = ('user',)
    filter_horizontal = ('pair_stimuli', 'qc_stimuli')

    @admin.display(description='Stimuli')
    def stimulus_count(self, obj: StudyAssignment) -> int:
        # Only the side matching the study's mode is ever consulted.
        return obj.stimuli().count()


class CustomUserAdmin(UserAdmin):
    pass


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
