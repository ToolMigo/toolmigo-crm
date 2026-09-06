def active_membership(request):
    from django.conf import settings
    return {'active_organization':getattr(request,'organization',None),'active_membership':getattr(request,'membership',None),'app_version':settings.APP_VERSION,'available_version':settings.AVAILABLE_VERSION}
