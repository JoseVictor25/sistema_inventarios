from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "usuarios"
urlpatterns = [
    path("usuarios/", views.lista, name="lista"),
    path("usuarios/nuevo/", views.usuario_crear, name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/roles/", views.rol_lista, name="rol_lista"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
