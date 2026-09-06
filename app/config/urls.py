from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
urlpatterns = [
    path('favicon.ico',RedirectView.as_view(url='/static/img/toolmigo-logo.jpeg',permanent=True),name='favicon'),
    path('django-admin/', admin.site.urls),
    path('', include('core.urls')),
]
