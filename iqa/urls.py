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
            redirect_authenticated_user=True,
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
        'study/<int:study_id>/done/',
        views.study_done,
        name='study_done',
    ),
    path(
        'study/<int:study_id>/preload-manifest/',
        views.preload_manifest,
        name='preload_manifest',
    ),
    path(
        'preload-sw.js',
        views.preload_service_worker,
        name='preload_service_worker',
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
        'responses/',
        views.view_responses,
        name='view_responses',
    ),
    path(
        'responses/export/<int:study_id>/',
        views.export_responses_csv,
        name='export_csv',
    ),
    path(
        'responses/export-own/<int:study_id>/',
        views.export_own_responses_csv,
        name='export_own_csv',
    ),
]
