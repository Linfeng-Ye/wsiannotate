from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from .models import (
    Image, Study, MOSStimulus, PairStimulus,
    MOSResponse, PairResponse,
)
from .samplers import (
    get_next_stimulus, get_upcoming_stimuli, ordered_stimuli,
)


class OverwriteResubmitTests(TestCase):
    """Previous + resubmit must update the existing row, never duplicate."""

    def setUp(self):
        self.user = User.objects.create_user('ann01', password='x')
        self.client.force_login(self.user)
        self.img_a = Image.objects.create(fname='images/a.png', name='a')
        self.img_b = Image.objects.create(fname='images/b.png', name='b')

    def test_mos_resubmit_overwrites(self):
        study = Study.objects.create(
            name='m', mode=Study.MODE_MOS, is_active=True,
            scale_min=1, scale_max=5,
        )
        stim = MOSStimulus.objects.create(study=study, image=self.img_a)

        self.client.post(reverse('iqa:evaluation_submit'), {
            'study_id': study.id, 'stimulus_id': stim.id, 'score': '2',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.post(reverse('iqa:evaluation_submit'), {
            'study_id': study.id, 'stimulus_id': stim.id, 'score': '5',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        responses = MOSResponse.objects.filter(stimulus=stim, user=self.user)
        self.assertEqual(responses.count(), 1)
        self.assertEqual(responses.first().score, 5)

    def test_pair_resubmit_overwrites(self):
        study = Study.objects.create(
            name='p', mode=Study.MODE_2AFC, is_active=True,
        )
        stim = PairStimulus.objects.create(
            study=study, image_a=self.img_a, image_b=self.img_b,
        )

        self.client.post(reverse('iqa:evaluation_submit'), {
            'study_id': study.id, 'stimulus_id': stim.id, 'choice': 'A',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.post(reverse('iqa:evaluation_submit'), {
            'study_id': study.id, 'stimulus_id': stim.id, 'choice': 'B',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        responses = PairResponse.objects.filter(stimulus=stim, user=self.user)
        self.assertEqual(responses.count(), 1)
        self.assertEqual(responses.first().choice, 'B')


class SamplerAndPrefetchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ann02', password='x')
        self.client.force_login(self.user)
        self.study = Study.objects.create(
            name='s', mode=Study.MODE_2AFC, is_active=True,
            sampler=Study.SAMPLER_RANDOM,
        )
        self.imgs = [
            Image.objects.create(fname=f'images/{i}.png', name=str(i))
            for i in range(12)
        ]
        for i in range(10):
            PairStimulus.objects.create(
                study=self.study, image_a=self.imgs[i],
                image_b=self.imgs[i + 1], order=i,
            )

    def test_random_order_is_deterministic_per_user(self):
        order1 = [s.id for s in ordered_stimuli(self.study, self.user)]
        order2 = [s.id for s in ordered_stimuli(self.study, self.user)]
        self.assertEqual(order1, order2)

    def test_upcoming_follows_next_and_excludes_answered(self):
        first = get_next_stimulus(self.study, self.user)
        upcoming = get_upcoming_stimuli(
            self.study, self.user, first.id, 8,
        )
        self.assertNotIn(first.id, [s.id for s in upcoming])
        self.assertLessEqual(len(upcoming), 8)
        # The first upcoming stimulus is the one served after `first`.
        full = [s.id for s in ordered_stimuli(self.study, self.user)]
        self.assertEqual(upcoming[0].id, full[full.index(first.id) + 1])

    def test_prefetch_endpoint_returns_image_urls(self):
        first = get_next_stimulus(self.study, self.user)
        resp = self.client.get(
            reverse('iqa:prefetch', args=[self.study.id]),
            {'current': first.id},
        )
        self.assertEqual(resp.status_code, 200)
        images = resp.json()['images']
        self.assertTrue(images)
        self.assertTrue(all(u.startswith('http') for u in images))
        self.assertEqual(
            self.client.post(
                reverse('iqa:prefetch', args=[self.study.id]),
            ).status_code,
            405,
        )

    def test_prefetch_returns_complete_shared_reference_window(self):
        study = Study.objects.create(
            name='window', mode=Study.MODE_2AFC, is_active=True,
            sampler=Study.SAMPLER_SEQUENTIAL,
        )
        stimuli = []
        for i in range(9):
            image_a = Image.objects.create(
                fname=f'images/window/{i}_a.png', name=f'{i}_a',
            )
            image_b = Image.objects.create(
                fname=f'images/window/{i}_b.png', name=f'{i}_b',
            )
            reference = Image.objects.create(
                fname=f'images/window/{i}_ref.png', name=f'{i}_ref',
            )
            stimuli.append(PairStimulus.objects.create(
                study=study, image_a=image_a, image_b=image_b,
                reference_a=reference, reference_b=reference, order=i,
            ))

        response = self.client.get(
            reverse('iqa:prefetch', args=[study.id]),
            {'current': stimuli[0].id},
        )

        self.assertEqual(response.status_code, 200)
        images = response.json()['images']
        self.assertEqual(len(images), 24)
        self.assertEqual(len(set(images)), 24)
        self.assertTrue(images[0].endswith('/1_ref.png'))
        self.assertTrue(images[-1].endswith('/8_b.png'))

    def test_prefetch_caps_distinct_reference_trials_at_24_images(self):
        study = Study.objects.create(
            name='distinct', mode=Study.MODE_2AFC, is_active=True,
            sampler=Study.SAMPLER_SEQUENTIAL,
        )
        stimuli = []
        for i in range(9):
            images = [
                Image.objects.create(
                    fname=f'images/distinct/{i}_{part}.png',
                    name=f'{i}_{part}',
                )
                for part in ('a', 'b', 'ra', 'rb')
            ]
            stimuli.append(PairStimulus.objects.create(
                study=study, image_a=images[0], image_b=images[1],
                reference_a=images[2], reference_b=images[3], order=i,
            ))

        response = self.client.get(
            reverse('iqa:prefetch', args=[study.id]),
            {'current': stimuli[0].id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['images']), 24)

    def test_prefetch_rejects_inactive_study_and_anonymous_user(self):
        first = get_next_stimulus(self.study, self.user)
        self.study.is_active = False
        self.study.save(update_fields=['is_active'])

        response = self.client.get(
            reverse('iqa:prefetch', args=[self.study.id]),
            {'current': first.id},
        )
        self.assertEqual(response.status_code, 404)

        self.client.logout()
        response = self.client.get(
            reverse('iqa:prefetch', args=[self.study.id]),
            {'current': first.id},
        )
        self.assertEqual(response.status_code, 302)

    def test_prefetch_report_is_post_only_and_tolerates_bad_json(self):
        url = reverse('iqa:prefetch_report')
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(
            url, data=b'{not-json', content_type='application/json',
        )
        self.assertEqual(response.status_code, 204)

        self.client.logout()
        response = self.client.post(
            url, data=b'{}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

    def test_prefetch_report_tolerates_non_object_and_large_payloads(self):
        url = reverse('iqa:prefetch_report')
        response = self.client.post(
            url, data=b'[]', content_type='application/json',
        )
        self.assertEqual(response.status_code, 204)
        response = self.client.post(
            url, data=b'x' * 2049, content_type='application/json',
        )
        self.assertEqual(response.status_code, 204)

    def test_all_answered_has_no_next_stimulus(self):
        for stimulus in self.study.pair_stimuli.all():
            PairResponse.objects.create(
                stimulus=stimulus, user=self.user, choice='A',
            )
        self.assertIsNone(get_next_stimulus(self.study, self.user))
        self.assertEqual(
            get_upcoming_stimuli(self.study, self.user, None, 8), [],
        )

    def test_mos_upcoming_skips_answered_with_invalid_current(self):
        study = Study.objects.create(
            name='mos', mode=Study.MODE_MOS, is_active=True,
            sampler=Study.SAMPLER_SEQUENTIAL,
        )
        stimuli = [
            MOSStimulus.objects.create(
                study=study, image=self.imgs[i], order=i,
            )
            for i in range(3)
        ]
        MOSResponse.objects.create(
            stimulus=stimuli[0], user=self.user, score=3,
        )

        upcoming = get_upcoming_stimuli(study, self.user, 999999, 8)

        self.assertEqual([item.id for item in upcoming], [
            stimuli[1].id, stimuli[2].id,
        ])

    def test_least_evaluated_orders_unanswered_stimulus_first(self):
        study = Study.objects.create(
            name='least', mode=Study.MODE_2AFC, is_active=True,
            sampler=Study.SAMPLER_LEAST_EVAL,
        )
        first = PairStimulus.objects.create(
            study=study, image_a=self.imgs[0], image_b=self.imgs[1],
            order=0,
        )
        second = PairStimulus.objects.create(
            study=study, image_a=self.imgs[2], image_b=self.imgs[3],
            order=1,
        )
        other = User.objects.create_user('other', password='x')
        PairResponse.objects.create(
            stimulus=first, user=other, choice='A',
        )

        order = ordered_stimuli(study, self.user)

        self.assertEqual([item.id for item in order], [second.id, first.id])

    def test_previous_fallback_uses_the_user_sampler_order(self):
        order = ordered_stimuli(self.study, self.user)
        current = order[3]
        expected_previous = order[2]
        for stimulus in order[:3]:
            PairResponse.objects.create(
                stimulus=stimulus, user=self.user, choice='A',
            )

        response = self.client.post(reverse('iqa:previous_stimulus'), {
            'study_id': self.study.id,
            'stimulus_id': current.id,
        })

        self.assertRedirects(
            response,
            reverse('iqa:pair_evaluation', kwargs={
                'study_id': self.study.id,
                'stimulus_id': expected_previous.id,
            }),
            fetch_redirect_response=False,
        )

    def test_removed_routes_are_gone(self):
        for name in [
            'local_annotation', 'local_assignment',
            'preload_manifest', 'preload_service_worker',
        ]:
            with self.assertRaises(NoReverseMatch):
                reverse(f'iqa:{name}', args=[self.study.id])


class StaffDashboardTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'boss', password='x', is_staff=True,
        )
        self.ann = User.objects.create_user('worker', password='x')
        self.img = Image.objects.create(fname='images/x.png', name='x')
        self.study = Study.objects.create(
            name='S', mode=Study.MODE_2AFC, is_active=True,
        )
        self.stim = PairStimulus.objects.create(
            study=self.study, image_a=self.img, image_b=self.img,
        )
        PairResponse.objects.create(
            stimulus=self.stim, user=self.ann, choice='A',
        )

    def test_progress_requires_staff(self):
        self.client.force_login(self.ann)
        r = self.client.get(reverse('iqa:annotator_progress'))
        self.assertIn(r.status_code, (302, 403))

    def test_progress_lists_users_and_counts(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse('iqa:annotator_progress'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'worker')
        self.assertContains(r, '1/1')  # done/total for the answered study

    def test_per_user_export(self):
        self.client.force_login(self.staff)
        r = self.client.get(
            reverse('iqa:export_user_csv', args=[self.ann.id])
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv')
        body = r.content.decode().splitlines()
        self.assertEqual(len(body), 2)  # header + 1 response
        self.assertIn('worker_responses.csv', r['Content-Disposition'])

    def test_per_user_export_requires_staff(self):
        url = reverse('iqa:export_user_csv', args=[self.ann.id])
        self.client.force_login(self.ann)
        self.assertIn(self.client.get(url).status_code, (302, 403))
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_progress_and_export_include_mos_responses(self):
        mos_study = Study.objects.create(
            name='MOS study', mode=Study.MODE_MOS, is_active=True,
        )
        mos_stimulus = MOSStimulus.objects.create(
            study=mos_study, image=self.img,
        )
        MOSResponse.objects.create(
            stimulus=mos_stimulus, user=self.ann, score=4,
        )
        self.client.force_login(self.staff)

        progress = self.client.get(reverse('iqa:annotator_progress'))
        export = self.client.get(
            reverse('iqa:export_user_csv', args=[self.ann.id])
        )

        self.assertEqual(progress.status_code, 200)
        self.assertContains(progress, 'MOS study')
        rows = export.content.decode().splitlines()
        self.assertEqual(len(rows), 3)  # header + pair + MOS
        self.assertTrue(any('MOS study,MOS' in row for row in rows))

    def test_export_escapes_spreadsheet_formulas(self):
        self.study.name = '\t=DANGEROUS()'
        self.study.save(update_fields=['name'])
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse('iqa:export_user_csv', args=[self.ann.id])
        )

        self.assertContains(response, "'\t=DANGEROUS()")


class HealthCheckMiddlewareTests(SimpleTestCase):
    @override_settings(ALLOWED_HOSTS=[])
    def test_health_check_bypasses_host_validation(self):
        response = self.client.get('/healthz', HTTP_HOST='10.0.0.17')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')

    @override_settings(ALLOWED_HOSTS=[])
    def test_non_health_request_still_validates_host(self):
        response = self.client.get('/iqa/login/', HTTP_HOST='10.0.0.17')
        self.assertEqual(response.status_code, 400)
