from django.urls import path
from django.contrib.auth import views as auth
from logistica import views
urlpatterns=[path('',views.home,name='home'),path('entrar/',auth.LoginView.as_view(template_name='registration/login.html'),name='login'),path('sair/',auth.LogoutView.as_view(),name='logout'),path('senha/',auth.PasswordChangeView.as_view(template_name='registration/password.html',success_url='/'),name='password'),path('pedidos/novo/',views.new_order,name='new_order'),path('pedidos/<int:pk>/',views.detail,name='detail'),path('obras/',views.projects,name='projects'),path('equipe/',views.employees,name='employees'),path('equipe/<int:pk>/',views.edit_employee,name='edit_employee'),path('historico/',views.audit,name='audit'),path('health/',views.health,name='health')]
