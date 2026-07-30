from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'iqa'

urlpatterns = [
    path(
        '', views.login_redirect,
        name='login_redirect',
    ),
    path('home/', views.home, name='home'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='iqa/login.html',
            # Deliberately NOT redirect_authenticated_user: LoginView.dispatch()
            # applies that before post(), so an already-signed-in browser
            # posting the form is bounced to the success URL with its username
            # and password never checked. On a shared machine that silently
            # drops the second rater into the first one's session and
            # misattributes their answers -- and a wrong password looks
            # identical to a correct one. Letting the POST through means
            # credentials are validated and login() switches the session to
            # whoever actually authenticated.
        ),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(
            next_page='iqa:login',
        ),
        name='logout',
    ),
    path(
        'next-stimulus/',
        views.next_stimulus,
        name='next_stimulus',
    ),
    path(
        'previous-stimulus/',
        views.previous_stimulus,
        name='previous_stimulus',
    ),
    path(
        'study/<int:study_id>/done/',
        views.study_done,
        name='study_done',
    ),
    path(
        'study/<int:study_id>/prefetch/',
        views.prefetch,
        name='prefetch',
    ),
    path(
        'prefetch-report/',
        views.prefetch_report,
        name='prefetch_report',
    ),
    path(
        'evaluate/mos/<int:study_id>/'
        '<int:stimulus_id>/',
        views.mos_evaluation,
        name='mos_evaluation',
    ),
    path(
        'evaluate/pair/<int:study_id>/'
        '<int:stimulus_id>/',
        views.pair_evaluation,
        name='pair_evaluation',
    ),
    path(
        'submit/',
        views.evaluation_submit,
        name='evaluation_submit',
    ),
    path(
        'submit-batch/',
        views.evaluation_submit_batch,
        name='evaluation_submit_batch',
    ),
    path(
        'study/<int:study_id>/run/',
        views.local_run,
        name='local_run',
    ),
    path(
        'study/<int:study_id>/manifest/',
        views.study_manifest,
        name='study_manifest',
    ),
    path(
        'study/<int:study_id>/answered/',
        views.study_answered,
        name='study_answered',
    ),
    path(
        'bulk-create-users/',
        views.bulk_create_users,
        name='bulk_create_users',
    ),
    path(
        'user-creation-results/',
        views.user_creation_results,
        name='user_creation_results',
    ),
    path(
        'annotators/',
        views.annotator_progress,
        name='annotator_progress',
    ),
    path(
        'responses/',
        views.view_responses,
        name='view_responses',
    ),
    path(
        'responses/export-user/<int:user_id>/',
        views.export_user_responses_csv,
        name='export_user_csv',
    ),
    path(
        'responses/export/<int:study_id>/',
        views.export_responses_csv,
        name='export_csv',
    ),
    path(
        'responses/export/<int:study_id>/user/<int:user_id>/',
        views.export_study_user_csv,
        name='export_study_user_csv',
    ),
    path(
        'responses/export-own/<int:study_id>/',
        views.export_own_responses_csv,
        name='export_own_csv',
    ),
]
