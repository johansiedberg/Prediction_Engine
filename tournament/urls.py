from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, dashboard_view, predictions_view, upload_avatar_view,
    hub_view, herrklubb_view, vote_bucket_item, toggle_bucket_dream,
    add_bucket_item, complete_bucket_item, save_user_bucket_votes,
    calendar_view, add_unavailability_view, delete_unavailability_view,
    save_herrklubb_event_view, delete_herrklubb_event_view, toggle_event_coordinator_view
)

urlpatterns = [
    path('', CustomLoginView.as_view(), name='login'),
    path('hub/', hub_view, name='hub'),
    path('herrklubb/', herrklubb_view, name='herrklubb'),
    path('herrklubb/save/', save_user_bucket_votes, name='herrklubb_save_votes'),
    path('herrklubb/vote/', vote_bucket_item, name='herrklubb_vote'),
    path('herrklubb/dream/', toggle_bucket_dream, name='herrklubb_dream'),
    path('herrklubb/add/', add_bucket_item, name='herrklubb_add_item'),
    path('herrklubb/complete/<int:item_id>/', complete_bucket_item, name='herrklubb_complete_item'),
    path('herrklubb/kalender/', calendar_view, name='calendar'),
    path('herrklubb/kalender/add/', add_unavailability_view, name='add_unavailability'),
    path('herrklubb/kalender/delete/<int:item_id>/', delete_unavailability_view, name='delete_unavailability'),
    path('herrklubb/event/save/', save_herrklubb_event_view, name='save_herrklubb_event'),
    path('herrklubb/event/delete/<int:event_id>/', delete_herrklubb_event_view, name='delete_herrklubb_event'),
    path('herrklubb/event/coordinator/<int:event_id>/', toggle_event_coordinator_view, name='toggle_event_coordinator'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('predictions/', predictions_view, name='predictions'),
    path('profile/avatar/', upload_avatar_view, name='upload_avatar'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
]
