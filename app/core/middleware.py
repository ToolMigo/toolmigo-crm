class ActiveOrganizationMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        request.organization=None; request.membership=None
        if request.user.is_authenticated:
            memberships=request.user.memberships.select_related('organization').filter(is_active=True,is_removed=False,organization__is_active=True)
            selected=request.session.get('organization_id')
            membership=memberships.filter(organization_id=selected).first() if selected else memberships.first()
            if membership:
                request.organization=membership.organization; request.membership=membership
                request.session['organization_id']=str(membership.organization_id)
        return self.get_response(request)
