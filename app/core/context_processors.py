def active_membership(request):
    return {'active_organization':getattr(request,'organization',None),'active_membership':getattr(request,'membership',None)}
