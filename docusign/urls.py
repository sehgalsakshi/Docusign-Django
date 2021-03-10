from docusign import views
from django.conf.urls import url
from django.urls import reverse_lazy
from django.conf.urls import url
from .views import sign_complete, auth_callback, embedded_signing_ceremony


app_name = 'docusign'

urlpatterns = [
# url(r'^get_access_code/$', views.get_access_code, name='get_access_code'),
# url(r'^auth_login/', views.auth_login, name='auth_login'),
url(r'^sign_completed/$', views.sign_complete, name='sign_completed'),
url(r'^callback/$', views.auth_callback, name="auth_callback"),
url(r'^get_signing_url/$', views.embedded_signing_ceremony, name='get_signing_url'),

]

