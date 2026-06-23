from django.db import models
from django.contrib.auth.models import User


class Image(models.Model):
    fname = models.ImageField(upload_to='images/')
    name = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return self.name or str(self.fname)


class Study(models.Model):
    MODE_MOS = 'MOS'
    MODE_2AFC = '2AFC'
    MODE_CHOICES = [
        (MODE_MOS, 'Mean Opinion Score'),
        (MODE_2AFC, 'Two-Alternative Forced Choice'),
    ]

    SAMPLER_SEQUENTIAL = 'sequential'
    SAMPLER_RANDOM = 'random'
    SAMPLER_LEAST_EVAL = 'least_evaluated'
    SAMPLER_CHOICES = [
        (SAMPLER_SEQUENTIAL, 'Sequential'),
        (SAMPLER_RANDOM, 'Random'),
        (SAMPLER_LEAST_EVAL, 'Least Evaluated First'),
    ]

    SIZING_FIT = 'fit_screen'
    SIZING_ORIGINAL = 'original'
    SIZING_SCALED = 'scaled'
    SIZING_CHOICES = [
        (SIZING_FIT, 'Fit to screen'),
        (SIZING_ORIGINAL, 'Original size'),
        (SIZING_SCALED, 'Scaled by factor'),
    ]

    name = models.CharField(max_length=300)
    mode = models.CharField(
        max_length=4, choices=MODE_CHOICES,
    )
    prompt = models.TextField(blank=True)
    scale_min = models.IntegerField(default=1)
    scale_max = models.IntegerField(default=5)
    scale_min_label = models.CharField(
        max_length=100, default='Bad',
    )
    scale_max_label = models.CharField(
        max_length=100, default='Excellent',
    )
    is_active = models.BooleanField(default=False)
    sampler = models.CharField(
        max_length=20,
        choices=SAMPLER_CHOICES,
        default=SAMPLER_SEQUENTIAL,
    )
    image_sizing = models.CharField(
        max_length=12,
        choices=SIZING_CHOICES,
        default=SIZING_FIT,
    )
    image_scale_factor = models.FloatField(
        default=1.0,
        help_text='Only used when image_sizing is '
                  '"scaled".',
    )
    mos_use_textbox = models.BooleanField(
        default=False,
        help_text='MOS mode: use a free-text input '
                  'instead of score buttons.',
    )
    zoom_enabled = models.BooleanField(
        default=False,
        help_text='Show a magnified overlay when '
                  'hovering over images.',
    )
    zoom_factor = models.FloatField(
        default=2.0,
        help_text='Magnification factor for the '
                  'zoom overlay.',
    )
    allow_self_export = models.BooleanField(
        default=False,
        help_text='Allow participants to download '
                  'their own responses as a CSV.',
    )
    pair_shared_ref_layout = models.BooleanField(
        default=False,
        help_text='2AFC mode: lay out Image A, the '
                  'shared reference, and Image B in a '
                  'single row.  Requires '
                  'reference_a == reference_b for each '
                  'pair; pairs with mismatched '
                  'references fall back to the classic '
                  'layout.',
    )

    class Meta:
        verbose_name_plural = 'studies'

    def __str__(self) -> str:
        return f'{self.name} ({self.mode})'

    def stimulus_count(self) -> int:
        if self.mode == self.MODE_MOS:
            return self.mos_stimuli.count()
        return self.pair_stimuli.count()


class MOSStimulus(models.Model):
    study = models.ForeignKey(
        Study,
        on_delete=models.CASCADE,
        related_name='mos_stimuli',
    )
    image = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        related_name='+',
    )
    reference = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'MOS stimulus'
        verbose_name_plural = 'MOS stimuli'

    def __str__(self) -> str:
        ref = ''
        if self.reference:
            ref = f' (ref: {self.reference})'
        return f'MOS #{self.order}: {self.image}{ref}'


class PairStimulus(models.Model):
    study = models.ForeignKey(
        Study,
        on_delete=models.CASCADE,
        related_name='pair_stimuli',
    )
    image_a = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        related_name='+',
    )
    image_b = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        related_name='+',
    )
    reference_a = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    reference_b = models.ForeignKey(
        Image,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'pair stimulus'
        verbose_name_plural = 'pair stimuli'

    def __str__(self) -> str:
        return (
            f'Pair #{self.order}: '
            f'{self.image_a} vs {self.image_b}'
        )


class MOSResponse(models.Model):
    stimulus = models.ForeignKey(
        MOSStimulus, on_delete=models.PROTECT,
    )
    user = models.ForeignKey(
        User, on_delete=models.PROTECT,
    )
    score = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['stimulus', 'user']

    def __str__(self) -> str:
        return (
            f'{self.user}: '
            f'{self.stimulus} = {self.score}'
        )


class PairResponse(models.Model):
    CHOICE_A = 'A'
    CHOICE_B = 'B'
    CHOICE_CHOICES = [
        (CHOICE_A, 'Image A'),
        (CHOICE_B, 'Image B'),
    ]

    stimulus = models.ForeignKey(
        PairStimulus, on_delete=models.PROTECT,
    )
    user = models.ForeignKey(
        User, on_delete=models.PROTECT,
    )
    choice = models.CharField(
        max_length=1, choices=CHOICE_CHOICES,
    )
    display_choice = models.CharField(
        max_length=1, blank=True, null=True,
    )
    was_swapped = models.BooleanField(default=False)
    shown_image_a = models.CharField(
        max_length=512, blank=True,
    )
    shown_image_b = models.CharField(
        max_length=512, blank=True,
    )
    shown_reference_a = models.CharField(
        max_length=512, blank=True,
    )
    shown_reference_b = models.CharField(
        max_length=512, blank=True,
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['stimulus', 'user']

    def __str__(self) -> str:
        return (
            f'{self.user}: '
            f'{self.stimulus} = {self.choice}'
        )
