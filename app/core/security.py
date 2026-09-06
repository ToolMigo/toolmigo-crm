from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from .models import AuditEvent, Membership

def client_ip(request):
    forwarded=request.META.get('HTTP_X_FORWARDED_FOR','').split(',')[0].strip()
    return forwarded or request.META.get('REMOTE_ADDR')
def audit(request,action,target=None,metadata=None):
    AuditEvent.objects.create(organization=getattr(request,'organization',None),actor=request.user if request.user.is_authenticated else None,action=action,target_type=target.__class__.__name__ if target else '',target_id=str(target.pk) if target else '',metadata=metadata or {},ip_address=client_ip(request))
def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            membership=getattr(request,'membership',None)
            if not membership or membership.role not in roles:
                messages.error(request,'Je hebt onvoldoende rechten voor deze actie.')
                return redirect('dashboard')
            return view(request,*args,**kwargs)
        return wrapped
    return decorator
owner_required=roles_required(Membership.Role.OWNER)
