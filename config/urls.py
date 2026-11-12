"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from planner import views as planner_views
from planner.account_views import MemberPasswordResetView

urlpatterns = [
    path('', planner_views.signup, name='signup'),
    path('thanks/', planner_views.signup_complete, name='signup_complete'),
    path('login/', auth_views.LoginView.as_view(template_name='planner/login.html'), name='login'),
    path('password-reset/', MemberPasswordResetView.as_view(
        template_name='planner/password_reset_form.html',
        email_template_name='planner/emails/password_reset.txt',
        subject_template_name='planner/emails/password_reset_subject.txt',
    ), name='password_reset'),
    path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(template_name='planner/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='planner/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='planner/password_reset_complete.html'), name='password_reset_complete'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('my-account/', planner_views.member_portal, name='member_portal'),
    path('my-account/spending-statement/', planner_views.spending_statement, name='spending_statement'),
    path('my-account/guests/', planner_views.guest_list, name='guest_list'),
    path('my-account/shopping/', planner_views.shopping_management, name='shopping_management'),
    path('my-account/venues/', planner_views.venue_list, name='venue_list'),
    path('my-account/events/add/', planner_views.event_form, name='event_add'),
    path('my-account/events/<int:event_id>/', planner_views.event_detail, name='event_detail'),
    path('my-account/events/<int:event_id>/edit/', planner_views.event_form, name='event_edit'),
    path('my-account/events/<int:event_id>/shopping/', planner_views.event_shopping_list, name='event_shopping_list'),
    path('my-account/events/<int:event_id>/tables/', planner_views.table_plan, name='table_plan'),
    path('members/', planner_views.member_list, name='member_list'),
    path('members/<int:member_id>/status/', planner_views.member_status, name='member_status'),
    path('admin/', admin.site.urls),
]
