import os
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from core.models import AppointmentType, Board, BoardColumn, Membership, Organization, User
class Command(BaseCommand):
    help='Maak de eerste organisatie en beheerder aan vanuit omgevingsvariabelen.'
    @transaction.atomic
    def handle(self,*args,**options):
        email=os.environ.get('BOOTSTRAP_ADMIN_EMAIL','').strip().lower(); password=os.environ.get('BOOTSTRAP_ADMIN_PASSWORD','')
        org_name=os.environ.get('BOOTSTRAP_ORG_NAME','ToolMigo').strip()
        if not email or not password: self.stdout.write('Bootstrap overgeslagen: beheerder niet geconfigureerd.'); return
        org,_=Organization.objects.get_or_create(slug=slugify(org_name),defaults={'name':org_name})
        user,created=User.objects.get_or_create(email=email,defaults={'display_name':os.environ.get('BOOTSTRAP_ADMIN_NAME','Beheerder')})
        if created: user.set_password(password); user.save()
        Membership.objects.get_or_create(organization=org,user=user,defaults={'role':Membership.Role.OWNER})
        for name,color in [('Afspraak','#239F7F'),('Werkzaamheden','#2563EB'),('Telefonisch','#F59E0B'),('Deadline','#DC2626')]: AppointmentType.objects.get_or_create(organization=org,name=name,defaults={'color':color})
        board,_=Board.objects.get_or_create(organization=org,name='Werkbord',defaults={'is_default':True})
        for position,(name,color,done) in enumerate([('Inbox','#64748B',False),('Gepland','#2563EB',False),('Bezig','#F59E0B',False),('Wachten','#8B5CF6',False),('Afgerond','#239F7F',True)],1): BoardColumn.objects.get_or_create(board=board,name=name,defaults={'position':position,'color':color,'is_done':done})
        self.stdout.write(self.style.SUCCESS(f'Organisatie en beheerder gereed: {email}'))
