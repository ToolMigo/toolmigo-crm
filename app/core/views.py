from django.contrib import messages
import csv, hashlib, io, json, zipfile
import calendar
import base64, secrets
from decimal import Decimal
from datetime import timedelta
from datetime import date as date_cls, datetime
from django.contrib.auth import logout
from django.contrib.auth import login as auth_login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.core.mail import EmailMessage, get_connection
from django.conf import settings
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
import pyotp, qrcode
from .forms import AppointmentForm, BackupConfigurationForm, BoardColumnForm, BoardForm, ChecklistItemForm, ContactForm, CsvImportForm, CustomerForm, CustomerNoteForm, EmailTemplateForm, ExpenseForm, InvoiceForm, InvoiceLineForm, MileageEntryForm, OpportunityForm, OrganizationEmailSettingsForm, OrganizationSettingsForm, PaymentForm, ProductForm, ProfileForm, ProjectDocumentForm, ProjectForm, QuoteForm, QuoteLineForm, RecurringInvoiceScheduleForm, RejectionForm, ReminderPolicyForm, TaskAttachmentForm, TaskCommentForm, TaskForm, TeamMemberEditForm, TeamMemberForm, TimeEntryForm
from .models import Appointment, AppointmentType, AuditEvent, BackupConfiguration, Board, BoardColumn, Contact, Customer, CustomerActivity, DocumentSequence, EmailDelivery, EmailTemplate, Expense, Invoice, InvoiceLine, Membership, MileageEntry, Opportunity, OrganizationEmailSettings, Payment, PaymentReminder, PortalAccess, PortalDecision, Product, Project, ProjectDocument, Quote, QuoteLine, RecurringInvoiceSchedule, ReminderPolicy, Task, TaskAttachment, TaskChecklistItem, TaskComment, TimeEntry, User
from .pdf import build_invoice_pdf, build_quote_pdf
from .security import audit, owner_required, roles_required
from .backups import backup_file, create_backup, delete_backup, list_backups, request_restore, restore_status

class SecureLoginView(LoginView):
    template_name='core/login.html'; redirect_authenticated_user=True
    def key(self):
        ip=self.request.META.get('HTTP_X_FORWARDED_FOR',self.request.META.get('REMOTE_ADDR','')).split(',')[0].strip()
        email=self.request.POST.get('username','').strip().lower()
        return 'login:'+hashlib.sha256(f'{ip}|{email}'.encode()).hexdigest()
    def post(self,request,*args,**kwargs):
        if cache.get(self.key(),0)>=5:
            form=self.get_form(); form.add_error(None,'Te veel mislukte pogingen. Probeer het over 15 minuten opnieuw.')
            return self.form_invalid(form)
        return super().post(request,*args,**kwargs)
    def form_invalid(self,form):
        key=self.key(); attempts=cache.get(key,0)+1; cache.set(key,attempts,900)
        return super().form_invalid(form)
    def form_valid(self,form):
        cache.delete(self.key()); user=form.get_user()
        if user.totp_enabled:
            self.request.session.cycle_key(); self.request.session['pre_2fa_user_id']=user.pk; self.request.session['pre_2fa_backend']='django.contrib.auth.backends.ModelBackend'
            return redirect('two_factor_login')
        response=super().form_valid(form); AuditEvent.objects.create(actor=user,action='auth.login',ip_address=self.request.META.get('REMOTE_ADDR')); return response

def two_factor_login(request):
    user_id=request.session.get('pre_2fa_user_id')
    if not user_id: return redirect('login')
    user=get_object_or_404(User,pk=user_id,is_active=True,totp_enabled=True)
    if request.method=='POST':
        code=request.POST.get('code','').replace(' ','').strip(); valid=pyotp.TOTP(user.get_totp_secret()).verify(code,valid_window=1)
        recovery_index=next((i for i,value in enumerate(user.recovery_code_hashes) if check_password(code.upper(),value)),None) if not valid else None
        if valid or recovery_index is not None:
            if recovery_index is not None:
                hashes=list(user.recovery_code_hashes); hashes.pop(recovery_index); user.recovery_code_hashes=hashes; user.save(update_fields=['recovery_code_hashes'])
            backend=request.session.pop('pre_2fa_backend'); request.session.pop('pre_2fa_user_id',None); auth_login(request,user,backend=backend)
            membership=user.memberships.filter(is_active=True,is_removed=False).select_related('organization').first()
            AuditEvent.objects.create(actor=user,organization=membership.organization if membership else None,action='auth.login_2fa',ip_address=request.META.get('REMOTE_ADDR'))
            return redirect(request.POST.get('next') or 'dashboard')
        messages.error(request,'De verificatiecode is ongeldig.')
    return render(request,'core/two_factor_login.html')

@login_required
def two_factor_settings(request):
    if request.method=='POST' and request.POST.get('action')=='start':
        request.session['pending_totp_secret']=pyotp.random_base32(); return redirect('two_factor_settings')
    secret=request.session.get('pending_totp_secret')
    recovery_codes=request.session.pop('new_recovery_codes',None)
    if request.method=='POST' and request.POST.get('action')=='confirm' and secret:
        if pyotp.TOTP(secret).verify(request.POST.get('code','').strip(),valid_window=1):
            codes=[f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(10)]
            request.user.set_totp_secret(secret); request.user.totp_enabled=True; request.user.recovery_code_hashes=[make_password(c) for c in codes]; request.user.save(update_fields=['totp_secret_encrypted','totp_enabled','recovery_code_hashes']); request.session.pop('pending_totp_secret',None); request.session['new_recovery_codes']=codes
            audit(request,'auth.2fa_enabled',request.user); return redirect('two_factor_settings')
        messages.error(request,'De verificatiecode klopt niet.')
    uri=pyotp.TOTP(secret).provisioning_uri(name=request.user.email,issuer_name='ToolMigo CRM') if secret else None
    qr_data=None
    if uri:
        image=qrcode.make(uri); output=io.BytesIO(); image.save(output,format='PNG'); qr_data=base64.b64encode(output.getvalue()).decode()
    return render(request,'core/two_factor_settings.html',{'secret':secret,'qr_data':qr_data,'recovery_codes':recovery_codes})

@login_required
@require_POST
def two_factor_disable(request):
    code=request.POST.get('code','').strip()
    if not request.user.check_password(request.POST.get('password','')) or not pyotp.TOTP(request.user.get_totp_secret()).verify(code,valid_window=1):
        messages.error(request,'Wachtwoord of verificatiecode is onjuist.'); return redirect('two_factor_settings')
    request.user.totp_enabled=False; request.user.totp_secret_encrypted=''; request.user.recovery_code_hashes=[]; request.user.save(update_fields=['totp_enabled','totp_secret_encrypted','recovery_code_hashes']); audit(request,'auth.2fa_disabled',request.user); messages.success(request,'Tweestapsverificatie is uitgeschakeld.'); return redirect('two_factor_settings')

def health(request): return JsonResponse({'status':'ok'})

@login_required
def profile_settings(request):
    form=ProfileForm(request.POST or None,request.FILES or None,instance=request.user)
    if request.method=='POST' and form.is_valid():
        user=form.save(); audit(request,'profile.updated',user,{'theme':user.theme_preference,'avatar':bool(user.avatar)}); messages.success(request,'Je persoonlijke instellingen zijn opgeslagen.'); return redirect('profile_settings')
    return render(request,'core/profile_settings.html',{'form':form})

@login_required
def profile_avatar(request,user_id):
    allowed=User.objects.filter(Q(pk=request.user.pk)|Q(memberships__organization=request.organization,memberships__is_active=True)).distinct()
    user=get_object_or_404(allowed,pk=user_id,is_active=True)
    if not user.avatar: return HttpResponse(status=404)
    return FileResponse(user.avatar.open('rb'),content_type='image/*')

def organization_mail_connection(organization):
    try: config=organization.email_settings
    except OrganizationEmailSettings.DoesNotExist: raise ValueError('SMTP is nog niet ingesteld door de bedrijfsbeheerder.')
    if not config.is_active: raise ValueError('E-mailverzending is uitgeschakeld in de bedrijfsinstellingen.')
    connection=get_connection('django.core.mail.backends.smtp.EmailBackend',host=config.host,port=config.port,username=config.username or None,password=config.get_password() or None,use_tls=config.use_tls,use_ssl=config.use_ssl,fail_silently=False)
    return config,connection

@login_required
@owner_required
def email_settings(request):
    config,_=OrganizationEmailSettings.objects.get_or_create(organization=request.organization,defaults={'from_email':request.user.email})
    form=OrganizationEmailSettingsForm(request.POST or None,instance=config)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'organization.email_settings_updated',config,{'host':config.host,'port':config.port,'username':config.username,'from_email':config.from_email,'tls':config.use_tls,'ssl':config.use_ssl,'active':config.is_active}); messages.success(request,'De SMTP-instellingen zijn veilig opgeslagen.'); return redirect('email_settings')
    return render(request,'core/email_settings.html',{'form':form,'config':config})

@login_required
@owner_required
def organization_settings(request):
    form=OrganizationSettingsForm(request.POST or None,request.FILES or None,instance=request.organization)
    if request.method=='POST' and form.is_valid():
        organization=form.save(); audit(request,'organization.settings_updated',organization); messages.success(request,'De bedrijfsinstellingen zijn opgeslagen.'); return redirect('organization_settings')
    return render(request,'core/organization_settings.html',{'form':form})

@login_required
def organization_logo(request):
    if not request.organization or not request.organization.logo: raise Http404
    return FileResponse(request.organization.logo.open('rb'),content_type='image/*')

@login_required
@owner_required
@require_POST
def email_settings_test(request):
    try:
        config,connection=organization_mail_connection(request.organization); message=EmailMessage(f'Testmail van {request.organization.name}','De SMTP-instellingen van ToolMigo CRM werken correct.',config.from_email,[request.user.email],connection=connection); message.send(fail_silently=False); audit(request,'organization.email_test_sent',config,{'recipient':request.user.email}); messages.success(request,f'Testmail verzonden naar {request.user.email}.')
    except Exception as exc: messages.error(request,f'Testmail mislukt: {str(exc)[:500]}')
    return redirect('email_settings')

@login_required
def dashboard(request):
    if not request.organization: return render(request,'core/no_organization.html',status=403)
    team=request.organization.memberships.filter(is_active=True).select_related('user')
    is_owner=request.membership.role==Membership.Role.OWNER
    recent=request.organization.audit_events.select_related('actor')[:7] if is_owner else []
    customers=request.organization.customers.exclude(status=Customer.Status.ARCHIVED)
    quotes=request.organization.quotes.filter(is_archived=False)
    invoices=request.organization.invoices.filter(is_archived=False).prefetch_related('lines','payments')
    open_quotes=quotes.filter(status__in=[Quote.Status.DRAFT,Quote.Status.SUBMITTED,Quote.Status.APPROVED]).count()
    outstanding=sum((invoice.outstanding for invoice in invoices.filter(status__in=[Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.OVERDUE])),Decimal('0'))
    today=timezone.localdate(); now=timezone.now(); notifications=[]
    due_tasks=request.organization.tasks.filter(is_archived=False,completed_at__isnull=True,assignees=request.membership,due_date__lte=now+timedelta(days=2)).distinct()[:5]
    for task in due_tasks: notifications.append({'title':task.title,'detail':f'Taak verloopt {timezone.localtime(task.due_date).strftime("%d-%m-%Y %H:%M") if task.due_date else "binnenkort"}','url':reverse('task_detail',args=[task.board_id,task.id])})
    upcoming=request.organization.appointments.filter(is_cancelled=False,participants=request.membership,start__gte=now,start__lte=now+timedelta(days=2)).distinct()[:5]
    for item in upcoming: notifications.append({'title':item.title,'detail':f'Afspraak {timezone.localtime(item.start).strftime("%d-%m-%Y %H:%M")}','url':reverse('appointment_detail',args=[item.id])})
    if request.membership.role in (Membership.Role.OWNER,Membership.Role.BILLING):
        submitted=quotes.filter(status=Quote.Status.SUBMITTED).count()+invoices.filter(status=Invoice.Status.SUBMITTED).count()
        if submitted: notifications.insert(0,{'title':f'{submitted} document(en) wachten op goedkeuring','detail':'Controleer offertes en facturen.','url':reverse('quote_list')})
    return render(request,'core/dashboard.html',{'team_count':team.count(),'customer_count':customers.count(),'open_quote_count':open_quotes,'outstanding_total':outstanding,'notifications':notifications[:8],'recent_events':recent,'show_auditlog':is_owner})

@login_required
def global_search(request):
    query=request.GET.get('q','').strip(); results=[]
    if len(query)>=2:
        org=request.organization
        for obj in org.customers.exclude(status=Customer.Status.ARCHIVED).filter(Q(legal_name__icontains=query)|Q(trade_name__icontains=query)|Q(email__icontains=query))[:10]: results.append({'kind':'Klant','title':str(obj),'detail':obj.email,'url':reverse('customer_detail',args=[obj.id])})
        for obj in org.quotes.filter(is_archived=False).filter(Q(number__icontains=query)|Q(title__icontains=query)|Q(customer__legal_name__icontains=query))[:10]: results.append({'kind':'Offerte','title':str(obj),'detail':obj.title,'url':reverse('quote_detail',args=[obj.id])})
        for obj in org.invoices.filter(is_archived=False).filter(Q(number__icontains=query)|Q(title__icontains=query)|Q(customer__legal_name__icontains=query))[:10]: results.append({'kind':'Factuur','title':str(obj),'detail':obj.title,'url':reverse('invoice_detail',args=[obj.id])})
        for obj in org.tasks.filter(is_archived=False).filter(Q(title__icontains=query)|Q(description__icontains=query))[:10]: results.append({'kind':'Taak','title':obj.title,'detail':obj.get_priority_display(),'url':reverse('task_detail',args=[obj.board_id,obj.id])})
        for obj in org.appointments.filter(is_cancelled=False).filter(Q(title__icontains=query)|Q(location__icontains=query))[:10]: results.append({'kind':'Afspraak','title':obj.title,'detail':timezone.localtime(obj.start).strftime('%d-%m-%Y %H:%M'),'url':reverse('appointment_detail',args=[obj.id])})
    return render(request,'core/search.html',{'query':query,'results':results})

@login_required
@owner_required
def trash(request):
    cutoff=timezone.now()-timedelta(days=30); org=request.organization
    items=[]
    for obj in org.customers.filter(status=Customer.Status.ARCHIVED,archived_at__gte=cutoff): items.append({'kind':'Klant','title':str(obj),'archived_at':obj.archived_at,'restore_url':reverse('trash_restore',args=['customer',obj.id])})
    for model,kind,key in ((Quote,'Offerte','quote'),(Invoice,'Factuur','invoice'),(EmailDelivery,'Verzending','delivery')):
        for obj in model.objects.filter(organization=org,is_archived=True,archived_at__gte=cutoff): items.append({'kind':kind,'title':str(obj),'archived_at':obj.archived_at,'restore_url':reverse('trash_restore',args=[key,obj.id])})
    items.sort(key=lambda x:x['archived_at'] or timezone.now(),reverse=True)
    return render(request,'core/trash.html',{'items':items,'retention_days':30})

@login_required
@owner_required
@require_POST
def trash_restore(request,kind,object_id):
    mapping={'customer':Customer,'quote':Quote,'invoice':Invoice,'delivery':EmailDelivery}; model=mapping.get(kind)
    if not model: raise Http404
    obj=get_object_or_404(model,pk=object_id,organization=request.organization)
    if kind=='customer': obj.status=Customer.Status.ACTIVE; fields=['status','archived_at','archived_by','updated_at']
    else: obj.is_archived=False; fields=['is_archived','archived_at','archived_by']+(['updated_at'] if hasattr(obj,'updated_at') else [])
    obj.archived_at=None; obj.archived_by=None; obj.save(update_fields=fields); audit(request,f'{kind}.restored',obj); messages.success(request,f'{obj} is hersteld.'); return redirect('trash')

@login_required
@owner_required
def backups(request):
    config=BackupConfiguration.load(); form=BackupConfigurationForm(request.POST or None,instance=config)
    if request.method=='POST' and form.is_valid():
        config=form.save()
        from .backups import enforce_retention
        enforce_retention(config.max_backups); audit(request,'backup.settings_updated',config,{'max_backups':config.max_backups,'automatic_enabled':config.automatic_enabled,'frequency':config.frequency,'weekday':config.weekday,'run_at':str(config.run_at)})
        messages.success(request,'De back-upinstellingen zijn opgeslagen.'); return redirect('backups')
    return render(request,'core/backups.html',{'backups':list_backups(),'form':form,'config':config})

@login_required
@owner_required
@require_POST
def backup_create(request):
    try:
        folder=create_backup(); audit(request,'backup.created',metadata={'backup':folder.name}); messages.success(request,f'Back-up {folder.name} is veilig aangemaakt.')
    except Exception as exc:
        messages.error(request,f'Back-up maken mislukt: {str(exc)[:300]}')
    return redirect('backups')

@login_required
@owner_required
def backup_download(request,backup_name,filename):
    path=backup_file(backup_name,filename)
    if not path: raise Http404
    audit(request,'backup.downloaded',metadata={'backup':backup_name,'file':filename})
    return FileResponse(path.open('rb'),as_attachment=True,filename=f'{backup_name}-{filename}')

@login_required
@owner_required
@require_POST
def backup_delete(request,backup_name):
    try:
        if delete_backup(backup_name):
            audit(request,'backup.deleted',metadata={'backup':backup_name}); messages.success(request,'De back-up is verwijderd.')
        else: messages.error(request,'De back-up bestaat niet meer of is ondertussen automatisch verwijderd.')
    except OSError as exc: messages.error(request,f'Verwijderen mislukt: {str(exc)[:200]}')
    return redirect('backups')

@login_required
@owner_required
def backup_restore(request):
    if request.method=='POST':
        name=request.POST.get('backup','')
        try:
            request_restore(name); audit(request,'backup.restore_requested',metadata={'backup':name}); messages.warning(request,'De herstelopdracht is gestart. De CRM kan tijdelijk niet bereikbaar zijn.'); return redirect('backup_restore')
        except ValueError as exc: messages.error(request,str(exc))
    return render(request,'core/backup_restore.html',{'backups':list_backups(),'restore_status':restore_status()})

@login_required
def customer_list(request):
    qs=request.organization.customers.select_related('owner__user')
    query=request.GET.get('q','').strip(); status=request.GET.get('status','active'); kind=request.GET.get('kind','')
    if query: qs=qs.filter(Q(legal_name__icontains=query)|Q(trade_name__icontains=query)|Q(email__icontains=query)|Q(kvk_number__icontains=query)|Q(city__icontains=query)|Q(contacts__first_name__icontains=query)|Q(contacts__last_name__icontains=query)).distinct()
    if status!='all': qs=qs.filter(status=status)
    if kind: qs=qs.filter(kind=kind)
    page=Paginator(qs,25).get_page(request.GET.get('page'))
    counts={x['status']:x['count'] for x in request.organization.customers.values('status').annotate(count=Count('id'))}
    return render(request,'core/customer_list.html',{'page':page,'query':query,'selected_status':status,'selected_kind':kind,'counts':counts,'status_choices':Customer.Status.choices,'kind_choices':Customer.Kind.choices})

@login_required
def customer_detail(request,customer_id):
    customer=get_object_or_404(request.organization.customers.select_related('owner__user'),pk=customer_id)
    return render(request,'core/customer_detail.html',{'customer':customer,'contacts':customer.contacts.filter(is_active=True),'activities':customer.activities.select_related('actor')[:30],'note_form':CustomerNoteForm(),'documents':customer.documents.filter(project__isnull=True),'document_form':ProjectDocumentForm()})

@login_required
@require_POST
def customer_document_add(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); form=ProjectDocumentForm(request.POST,request.FILES)
    if form.is_valid():
        obj=form.save(False); obj.organization=request.organization; obj.customer=customer; obj.uploaded_by=request.user; obj.original_name=obj.file.name; obj.content_type=obj.file.content_type or ''; obj.size=obj.file.size; obj.save(); audit(request,'customer.document_added',obj); messages.success(request,'Klantdocument toegevoegd.')
    else: messages.error(request,'Controleer het document.')
    return redirect('customer_detail',customer.id)

@login_required
def customer_create(request):
    form=CustomerForm(request.POST or None,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        customer=form.save(); CustomerActivity.objects.create(organization=request.organization,customer=customer,actor=request.user,kind='system',body='Klantdossier aangemaakt.')
        audit(request,'customer.created',customer,{'name':customer.legal_name}); messages.success(request,'Het klantdossier is aangemaakt.'); return redirect('customer_detail',customer.id)
    return render(request,'core/customer_form.html',{'form':form,'heading':'Nieuwe klant','submit_label':'Klant aanmaken'})

@login_required
def customer_edit(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id)
    form=CustomerForm(request.POST or None,instance=customer,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        customer=form.save(); CustomerActivity.objects.create(organization=request.organization,customer=customer,actor=request.user,kind='system',body='Klantgegevens bijgewerkt.')
        audit(request,'customer.updated',customer); messages.success(request,'De klantgegevens zijn bijgewerkt.'); return redirect('customer_detail',customer.id)
    return render(request,'core/customer_form.html',{'form':form,'customer':customer,'heading':'Klant bewerken','submit_label':'Wijzigingen opslaan'})

@login_required
@require_POST
def customer_archive(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); customer.status=Customer.Status.ARCHIVED; customer.archived_at=timezone.now(); customer.archived_by=request.user; customer.save(update_fields=['status','archived_at','archived_by','updated_at'])
    CustomerActivity.objects.create(organization=request.organization,customer=customer,actor=request.user,kind='system',body='Klantdossier gearchiveerd.')
    audit(request,'customer.archived',customer); messages.success(request,'Het klantdossier is gearchiveerd.'); return redirect('customer_list')

@login_required
def contact_add(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); form=ContactForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        contact=form.save(False); contact.customer=customer; contact.save(); CustomerActivity.objects.create(organization=request.organization,customer=customer,actor=request.user,kind='system',body=f'Contactpersoon {contact} toegevoegd.')
        audit(request,'contact.created',contact,{'customer_id':str(customer.id)}); messages.success(request,'De contactpersoon is toegevoegd.'); return redirect('customer_detail',customer.id)
    return render(request,'core/contact_form.html',{'form':form,'customer':customer,'heading':'Contactpersoon toevoegen'})

@login_required
def contact_edit(request,customer_id,contact_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); contact=get_object_or_404(customer.contacts,pk=contact_id,is_active=True); form=ContactForm(request.POST or None,instance=contact)
    if request.method=='POST' and form.is_valid():
        contact=form.save(); audit(request,'contact.updated',contact,{'customer_id':str(customer.id)}); messages.success(request,'De contactpersoon is bijgewerkt.'); return redirect('customer_detail',customer.id)
    return render(request,'core/contact_form.html',{'form':form,'customer':customer,'heading':'Contactpersoon bewerken'})

@login_required
@require_POST
def contact_archive(request,customer_id,contact_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); contact=get_object_or_404(customer.contacts,pk=contact_id); contact.is_active=False; contact.is_primary=False; contact.save(update_fields=['is_active','is_primary','updated_at'])
    audit(request,'contact.archived',contact,{'customer_id':str(customer.id)}); messages.success(request,'De contactpersoon is verwijderd uit het actieve dossier.'); return redirect('customer_detail',customer.id)

@login_required
@require_POST
def customer_note(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id); form=CustomerNoteForm(request.POST)
    if form.is_valid():
        activity=CustomerActivity.objects.create(organization=request.organization,customer=customer,actor=request.user,kind=form.cleaned_data['kind'],body=form.cleaned_data['body'])
        audit(request,'customer.activity_added',activity,{'customer_id':str(customer.id),'kind':activity.kind}); messages.success(request,'De activiteit is aan het dossier toegevoegd.')
    else: messages.error(request,'De activiteit kon niet worden opgeslagen.')
    return redirect('customer_detail',customer.id)

@login_required
def customer_export(request):
    response=HttpResponse(content_type='text/csv; charset=utf-8'); response['Content-Disposition']='attachment; filename="toolmigo-klanten.csv"'; response.write('\ufeff')
    writer=csv.writer(response,delimiter=';'); writer.writerow(['type','naam','handelsnaam','e-mail','telefoon','kvk','btw-id','status','straat','postcode','plaats','betalingstermijn','labels'])
    for c in request.organization.customers.all(): writer.writerow([c.kind,c.legal_name,c.trade_name,c.email,c.phone,c.kvk_number,c.vat_id,c.status,c.address,c.postal_code,c.city,c.payment_term_days,', '.join(c.labels)])
    audit(request,'customer.exported',metadata={'count':request.organization.customers.count()}); return response

@login_required
@owner_required
def customer_import(request):
    form=CsvImportForm(request.POST or None,request.FILES or None); result=None
    if request.method=='POST' and form.is_valid():
        try:
            text=form.cleaned_data['file'].read().decode('utf-8-sig'); sample=text[:2048]; delimiter=csv.Sniffer().sniff(sample,delimiters=';,').delimiter; rows=csv.DictReader(io.StringIO(text),delimiter=delimiter)
            created=0; skipped=[]
            with transaction.atomic():
                for number,row in enumerate(rows,start=2):
                    name=(row.get('naam') or row.get('name') or '').strip()
                    if not name: skipped.append(f'Regel {number}: naam ontbreekt'); continue
                    kvk=''.join(filter(str.isdigit,row.get('kvk','')))
                    if kvk and request.organization.customers.filter(kvk_number=kvk).exists(): skipped.append(f'Regel {number}: KvK bestaat al'); continue
                    Customer.objects.create(organization=request.organization,kind=row.get('type') if row.get('type') in Customer.Kind.values else Customer.Kind.COMPANY,legal_name=name,trade_name=row.get('handelsnaam','').strip(),email=row.get('e-mail','').strip(),phone=row.get('telefoon','').strip(),kvk_number=kvk,vat_id=row.get('btw-id','').strip(),address=row.get('straat','').strip(),postal_code=row.get('postcode','').strip(),city=row.get('plaats','').strip(),status=row.get('status') if row.get('status') in Customer.Status.values else Customer.Status.ACTIVE,labels=[x.strip() for x in row.get('labels','').split(',') if x.strip()])
                    created+=1
            audit(request,'customer.imported',metadata={'created':created,'skipped':len(skipped)}); result={'created':created,'skipped':skipped}; messages.success(request,f'{created} klanten geïmporteerd.')
        except (UnicodeDecodeError,csv.Error) as exc: form.add_error('file',f'Het CSV-bestand kon niet worden gelezen: {exc}')
    return render(request,'core/customer_import.html',{'form':form,'result':result})

@login_required
def product_list(request):
    products=request.organization.products.order_by('-is_active','name'); return render(request,'core/product_list.html',{'products':products})

@login_required
def product_form(request,product_id=None):
    product=get_object_or_404(request.organization.products,pk=product_id) if product_id else None; form=ProductForm(request.POST or None,instance=product,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        product=form.save(); audit(request,'product.updated' if product_id else 'product.created',product); messages.success(request,'Product of dienst opgeslagen.'); return redirect('product_list')
    return render(request,'core/product_form.html',{'form':form,'product':product})

@login_required
@require_POST
def product_delete(request,product_id):
    product=get_object_or_404(request.organization.products,pk=product_id); label=f'{product.code} · {product.name}'; audit(request,'product.deleted',product,{'label':label}); product.delete(); messages.success(request,f'{label} is verwijderd.'); return redirect('product_list')

@login_required
def quote_list(request):
    qs=request.organization.quotes.filter(is_archived=False).select_related('customer','created_by'); status=request.GET.get('status','')
    if status: qs=qs.filter(status=status)
    return render(request,'core/quote_list.html',{'quotes':qs,'selected_status':status,'status_choices':Quote.Status.choices})

@login_required
def quote_create(request):
    days=request.organization.quote_valid_days; initial={'issue_date':timezone.localdate(),'valid_until':timezone.localdate()+timedelta(days=days),'terms':request.organization.default_quote_terms or f'Deze offerte is {days} dagen geldig.'}; form=QuoteForm(request.POST or None,initial=initial,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        quote=form.save(False); quote.created_by=request.user; quote.save(); audit(request,'quote.created',quote); messages.success(request,'Offerteconcept aangemaakt. Voeg nu regels toe.'); return redirect('quote_detail',quote.id)
    return render(request,'core/quote_form.html',{'form':form,'heading':'Nieuwe offerte'})

def scoped_quote(request,quote_id): return get_object_or_404(request.organization.quotes.filter(is_archived=False).select_related('customer','created_by','approved_by').prefetch_related('lines'),pk=quote_id)

@login_required
def quote_detail(request,quote_id):
    quote=scoped_quote(request,quote_id); return render(request,'core/quote_detail.html',{'quote':quote,'line_form':QuoteLineForm(organization=request.organization),'rejection_form':RejectionForm()})

@login_required
def quote_edit(request,quote_id):
    quote=scoped_quote(request,quote_id)
    if quote.status not in (Quote.Status.DRAFT,Quote.Status.REJECTED): messages.error(request,'Alleen een concept of afgewezen offerte kan worden bewerkt.'); return redirect('quote_detail',quote.id)
    form=QuoteForm(request.POST or None,instance=quote,organization=request.organization)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'quote.updated',quote); messages.success(request,'Offerte bijgewerkt.'); return redirect('quote_detail',quote.id)
    return render(request,'core/quote_form.html',{'form':form,'quote':quote,'heading':'Offerte bewerken'})

@login_required
@require_POST
def quote_delete(request,quote_id):
    quote=scoped_quote(request,quote_id)
    label=str(quote); quote.is_archived=True; quote.archived_at=timezone.now(); quote.archived_by=request.user; quote.save(update_fields=['is_archived','archived_at','archived_by','updated_at']); audit(request,'quote.archived',quote,{'label':label,'customer':str(quote.customer),'status':quote.status}); messages.success(request,'De offerte is uit het overzicht verwijderd en veilig gearchiveerd.'); return redirect('quote_list')

@login_required
@require_POST
def quote_line_add(request,quote_id):
    quote=scoped_quote(request,quote_id)
    if quote.status not in (Quote.Status.DRAFT,Quote.Status.REJECTED): return HttpResponse('Offerte is vergrendeld.',status=409)
    form=QuoteLineForm(request.POST,organization=request.organization)
    if form.is_valid():
        line=form.save(False); line.quote=quote; line.position=quote.lines.count()+1; line.save(); audit(request,'quote.line_added',line,{'quote_id':str(quote.id)}); messages.success(request,'Offerteregel toegevoegd.')
    else:
        for errors in form.errors.values(): messages.error(request,' '.join(errors))
    return redirect('quote_detail',quote.id)

@login_required
@require_POST
def quote_line_delete(request,quote_id,line_id):
    quote=scoped_quote(request,quote_id)
    if quote.status not in (Quote.Status.DRAFT,Quote.Status.REJECTED): return HttpResponse('Offerte is vergrendeld.',status=409)
    line=get_object_or_404(quote.lines,pk=line_id); audit(request,'quote.line_deleted',line,{'quote_id':str(quote.id)}); line.delete(); messages.success(request,'Offerteregel verwijderd.'); return redirect('quote_detail',quote.id)

@login_required
@require_POST
def quote_submit(request,quote_id):
    quote=scoped_quote(request,quote_id)
    if quote.status not in (Quote.Status.DRAFT,Quote.Status.REJECTED) or not quote.lines.exists(): messages.error(request,'Voeg minimaal één regel toe voordat je de offerte indient.'); return redirect('quote_detail',quote.id)
    quote.status=Quote.Status.SUBMITTED; quote.submitted_at=timezone.now(); quote.rejection_reason=''; quote.save(update_fields=['status','submitted_at','rejection_reason','updated_at']); audit(request,'quote.submitted',quote); messages.success(request,'Offerte staat klaar voor goedkeuring.'); return redirect('quote_detail',quote.id)

def can_approve(request,quote): return request.membership.role in (Membership.Role.OWNER,Membership.Role.BILLING) and quote.created_by_id!=request.user.id

@login_required
@require_POST
def quote_approve(request,quote_id):
    quote=scoped_quote(request,quote_id)
    if quote.status!=Quote.Status.SUBMITTED or not can_approve(request,quote): messages.error(request,'Je mag deze offerte niet goedkeuren.'); return redirect('quote_detail',quote.id)
    with transaction.atomic():
        sequence,_=DocumentSequence.objects.select_for_update().get_or_create(organization=request.organization,document_type='quote',year=timezone.localdate().year,defaults={'next_number':1})
        quote.number=f'{request.organization.quote_prefix}-{sequence.year}-{sequence.next_number:04d}'; sequence.next_number+=1; sequence.save(update_fields=['next_number'])
        quote.status=Quote.Status.APPROVED; quote.approved_by=request.user; quote.approved_at=timezone.now(); quote.save(update_fields=['number','status','approved_by','approved_at','updated_at'])
    audit(request,'quote.approved',quote,{'number':quote.number}); messages.success(request,f'Offerte {quote.number} is goedgekeurd.'); return redirect('quote_detail',quote.id)

@login_required
@require_POST
def quote_reject(request,quote_id):
    quote=scoped_quote(request,quote_id); form=RejectionForm(request.POST)
    if quote.status!=Quote.Status.SUBMITTED or not can_approve(request,quote) or not form.is_valid(): messages.error(request,'De offerte kon niet worden afgewezen.'); return redirect('quote_detail',quote.id)
    quote.status=Quote.Status.REJECTED; quote.rejection_reason=form.cleaned_data['reason']; quote.save(update_fields=['status','rejection_reason','updated_at']); audit(request,'quote.rejected',quote); messages.success(request,'Offerte teruggestuurd naar de maker.'); return redirect('quote_detail',quote.id)

@login_required
def quote_pdf(request,quote_id):
    quote=scoped_quote(request,quote_id); data=build_quote_pdf(quote); response=HttpResponse(data,content_type='application/pdf'); response['Content-Disposition']=f'inline; filename="offerte-{quote.number or "concept"}.pdf"'; return response

@login_required
def invoice_list(request):
    qs=request.organization.invoices.filter(is_archived=False).select_related('customer','created_by'); status=request.GET.get('status','')
    if status: qs=qs.filter(status=status)
    return render(request,'core/invoice_list.html',{'invoices':qs,'selected_status':status,'status_choices':Invoice.Status.choices,'approved_count':request.organization.invoices.filter(status=Invoice.Status.APPROVED,is_archived=False).count()+request.organization.quotes.filter(status=Quote.Status.APPROVED,is_archived=False).count()})

@login_required
def invoice_create(request):
    today=timezone.localdate(); initial={'issue_date':today,'delivery_date':today,'due_date':today+timedelta(days=request.organization.payment_term_days),'notes':request.organization.default_invoice_notes}; form=InvoiceForm(request.POST or None,initial=initial,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        invoice=form.save(False); invoice.created_by=request.user; invoice.save(); audit(request,'invoice.created',invoice); messages.success(request,'Factuurconcept aangemaakt.'); return redirect('invoice_detail',invoice.id)
    return render(request,'core/invoice_form.html',{'form':form,'heading':'Nieuwe factuur'})

@login_required
@require_POST
def invoice_from_quote(request,quote_id):
    quote=scoped_quote(request,quote_id)
    if quote.status not in (Quote.Status.APPROVED,Quote.Status.SENT,Quote.Status.ACCEPTED) or hasattr(quote,'invoice'): messages.error(request,'Deze offerte kan niet worden omgezet naar een factuur.'); return redirect('quote_detail',quote.id)
    today=timezone.localdate()
    with transaction.atomic():
        invoice=Invoice.objects.create(organization=request.organization,customer=quote.customer,source_quote=quote,created_by=request.user,title=quote.title,issue_date=today,delivery_date=today,due_date=today+timedelta(days=quote.customer.payment_term_days),notes=quote.terms)
        for line in quote.lines.all(): InvoiceLine.objects.create(organization=request.organization,invoice=invoice,position=line.position,description=line.description,quantity=line.quantity,unit=line.unit,unit_price=line.unit_price,discount_percent=line.discount_percent,vat_rate=line.vat_rate)
    audit(request,'invoice.created_from_quote',invoice,{'quote_id':str(quote.id)}); messages.success(request,'Factuurconcept gemaakt vanuit de offerte.'); return redirect('invoice_detail',invoice.id)

def scoped_invoice(request,invoice_id): return get_object_or_404(request.organization.invoices.filter(is_archived=False).select_related('customer','created_by','approved_by','original_invoice').prefetch_related('lines','payments'),pk=invoice_id)

@login_required
def invoice_detail(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id); return render(request,'core/invoice_detail.html',{'invoice':invoice,'line_form':InvoiceLineForm(),'payment_form':PaymentForm(initial={'paid_on':timezone.localdate()},invoice=invoice),'rejection_form':RejectionForm()})

@login_required
def invoice_edit(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status not in (Invoice.Status.DRAFT,Invoice.Status.REJECTED): messages.error(request,'Deze factuur is vergrendeld.'); return redirect('invoice_detail',invoice.id)
    form=InvoiceForm(request.POST or None,instance=invoice,organization=request.organization)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'invoice.updated',invoice); messages.success(request,'Factuur bijgewerkt.'); return redirect('invoice_detail',invoice.id)
    return render(request,'core/invoice_form.html',{'form':form,'invoice':invoice,'heading':'Factuur bewerken'})

@login_required
@require_POST
def invoice_delete(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    label=str(invoice); invoice.is_archived=True; invoice.archived_at=timezone.now(); invoice.archived_by=request.user; invoice.save(update_fields=['is_archived','archived_at','archived_by','updated_at']); audit(request,'invoice.archived',invoice,{'label':label,'customer':str(invoice.customer),'status':invoice.status}); messages.success(request,'De factuur is uit het overzicht verwijderd en veilig gearchiveerd.'); return redirect('invoice_list')

@login_required
@require_POST
def invoice_line_add(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status not in (Invoice.Status.DRAFT,Invoice.Status.REJECTED): return HttpResponse('Factuur is vergrendeld.',status=409)
    form=InvoiceLineForm(request.POST)
    if form.is_valid(): line=form.save(False); line.invoice=invoice; line.position=invoice.lines.count()+1; line.save(); audit(request,'invoice.line_added',line,{'invoice_id':str(invoice.id)}); messages.success(request,'Factuurregel toegevoegd.')
    else:
        for errors in form.errors.values(): messages.error(request,' '.join(errors))
    return redirect('invoice_detail',invoice.id)

@login_required
@require_POST
def invoice_line_delete(request,invoice_id,line_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status not in (Invoice.Status.DRAFT,Invoice.Status.REJECTED): return HttpResponse('Factuur is vergrendeld.',status=409)
    line=get_object_or_404(invoice.lines,pk=line_id); audit(request,'invoice.line_deleted',line); line.delete(); return redirect('invoice_detail',invoice.id)

@login_required
@require_POST
def invoice_submit(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status not in (Invoice.Status.DRAFT,Invoice.Status.REJECTED) or not invoice.lines.exists(): messages.error(request,'Voeg minimaal één regel toe.'); return redirect('invoice_detail',invoice.id)
    invoice.status=Invoice.Status.SUBMITTED; invoice.submitted_at=timezone.now(); invoice.rejection_reason=''; invoice.save(update_fields=['status','submitted_at','rejection_reason','updated_at']); audit(request,'invoice.submitted',invoice); return redirect('invoice_detail',invoice.id)

def can_approve_invoice(request,invoice): return request.membership.role in (Membership.Role.OWNER,Membership.Role.BILLING) and invoice.created_by_id!=request.user.id

@login_required
@require_POST
def invoice_approve(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status!=Invoice.Status.SUBMITTED or not can_approve_invoice(request,invoice): messages.error(request,'Je mag deze factuur niet goedkeuren.'); return redirect('invoice_detail',invoice.id)
    with transaction.atomic():
        seq,_=DocumentSequence.objects.select_for_update().get_or_create(organization=request.organization,document_type='invoice',year=timezone.localdate().year,defaults={'next_number':1}); invoice.number=f'{request.organization.invoice_prefix}-{seq.year}-{seq.next_number:04d}'; seq.next_number+=1; seq.save(update_fields=['next_number'])
        c=invoice.customer; invoice.customer_name_snapshot=c.legal_name; invoice.customer_address_snapshot=f'{c.billing_address or c.address}\n{c.billing_postal_code or c.postal_code} {c.billing_city or c.city}'.strip(); invoice.customer_vat_snapshot=c.vat_id; invoice.payment_reference=invoice.number; invoice.status=Invoice.Status.APPROVED; invoice.approved_by=request.user; invoice.approved_at=timezone.now(); invoice.save()
    audit(request,'invoice.approved',invoice,{'number':invoice.number}); messages.success(request,f'Factuur {invoice.number} is goedgekeurd.'); return redirect('invoice_detail',invoice.id)

@login_required
@require_POST
def invoice_reject(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id); form=RejectionForm(request.POST)
    if invoice.status!=Invoice.Status.SUBMITTED or not can_approve_invoice(request,invoice) or not form.is_valid(): messages.error(request,'Factuur kon niet worden afgewezen.'); return redirect('invoice_detail',invoice.id)
    invoice.status=Invoice.Status.REJECTED; invoice.rejection_reason=form.cleaned_data['reason']; invoice.save(update_fields=['status','rejection_reason','updated_at']); audit(request,'invoice.rejected',invoice); return redirect('invoice_detail',invoice.id)

@login_required
def invoice_pdf(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id); response=HttpResponse(build_invoice_pdf(invoice),content_type='application/pdf'); response['Content-Disposition']=f'inline; filename="factuur-{invoice.number or "concept"}.pdf"'; return response

def update_payment_status(invoice):
    if invoice.outstanding<=0: invoice.status=Invoice.Status.PAID
    elif invoice.paid_amount>0: invoice.status=Invoice.Status.PARTIAL
    elif invoice.due_date<timezone.localdate() and invoice.status==Invoice.Status.SENT: invoice.status=Invoice.Status.OVERDUE
    invoice.save(update_fields=['status','updated_at'])

@login_required
@require_POST
def payment_add(request,invoice_id):
    invoice=scoped_invoice(request,invoice_id)
    if invoice.status not in (Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.OVERDUE): messages.error(request,'Op deze factuur kan nog geen betaling worden geboekt.'); return redirect('invoice_detail',invoice.id)
    form=PaymentForm(request.POST,invoice=invoice)
    if form.is_valid():
        payment=form.save(False); payment.invoice=invoice; payment.recorded_by=request.user; payment.save()
        invoice._prefetched_objects_cache.pop('payments',None); update_payment_status(invoice)
        audit(request,'payment.recorded',payment,{'invoice_id':str(invoice.id),'amount':str(payment.amount)}); messages.success(request,'Betaling geregistreerd.')
    else:
        for errors in form.errors.values(): messages.error(request,' '.join(errors))
    return redirect('invoice_detail',invoice.id)

@login_required
@require_POST
def credit_create(request,invoice_id):
    original=scoped_invoice(request,invoice_id)
    if original.kind!=Invoice.Kind.INVOICE or original.status not in (Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.PAID,Invoice.Status.OVERDUE) or original.credit_invoices.exists(): messages.error(request,'Voor deze factuur kan geen creditfactuur worden gemaakt.'); return redirect('invoice_detail',original.id)
    with transaction.atomic():
        credit=Invoice.objects.create(organization=request.organization,customer=original.customer,original_invoice=original,created_by=request.user,kind=Invoice.Kind.CREDIT,title=f'Credit op {original.number}',issue_date=timezone.localdate(),delivery_date=original.delivery_date,due_date=timezone.localdate(),notes=f'Correctie op factuur {original.number}.')
        for x in original.lines.all(): InvoiceLine.objects.create(organization=request.organization,invoice=credit,position=x.position,description=x.description,quantity=x.quantity,unit=x.unit,unit_price=-x.unit_price,discount_percent=x.discount_percent,vat_rate=x.vat_rate)
    audit(request,'credit.created',credit,{'original_invoice_id':str(original.id)}); return redirect('invoice_detail',credit.id)

@login_required
@require_POST
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def dispatch_approved(request):
    docs=[('quote',x,x.customer.email,build_quote_pdf) for x in request.organization.quotes.filter(status=Quote.Status.APPROVED,is_archived=False).select_related('customer')]+[('invoice',x,x.customer.email,build_invoice_pdf) for x in request.organization.invoices.filter(status=Invoice.Status.APPROVED,is_archived=False).select_related('customer')]
    sent=failed=0
    for dtype,doc,recipient,pdf_builder in docs:
        label='Offerte' if dtype=='quote' else ('Creditfactuur' if doc.kind==Invoice.Kind.CREDIT else 'Factuur'); subject=f'{label} {doc.number} van {request.organization.name}'; delivery=EmailDelivery.objects.create(organization=request.organization,document_type=dtype,document_id=doc.id,recipient=recipient or 'ontbreekt@example.invalid',subject=subject,requested_by=request.user)
        try:
            if not recipient: raise ValueError('Klant heeft geen e-mailadres.')
            config,connection=organization_mail_connection(request.organization); email=EmailMessage(subject,f'Beste klant,\n\nIn de bijlage vindt u {label.lower()} {doc.number}.\n\nMet vriendelijke groet,\n{request.organization.name}',config.from_email,[recipient],connection=connection); email.attach(f'{dtype}-{doc.number}.pdf',pdf_builder(doc),'application/pdf'); email.send(fail_silently=False)
            delivery.status=EmailDelivery.Status.SENT; delivery.sent_at=timezone.now(); doc.status=Quote.Status.SENT if dtype=='quote' else Invoice.Status.SENT; doc.save(update_fields=['status','updated_at'])
            if dtype=='invoice' and doc.kind==Invoice.Kind.CREDIT and doc.original_invoice_id:
                Invoice.objects.filter(pk=doc.original_invoice_id,organization=request.organization).update(status=Invoice.Status.CREDITED,updated_at=timezone.now())
            sent+=1
        except Exception as exc: delivery.status=EmailDelivery.Status.FAILED; delivery.error=str(exc)[:2000]; failed+=1
        delivery.save(update_fields=['status','sent_at','error'])
    audit(request,'documents.batch_dispatched',metadata={'sent':sent,'failed':failed}); messages.success(request,f'Verzending afgerond: {sent} verzonden, {failed} mislukt.'); return redirect('outbox')

@login_required
def outbox(request): return render(request,'core/outbox.html',{'deliveries':request.organization.email_deliveries.filter(is_archived=False)[:100],'approved_count':request.organization.invoices.filter(status=Invoice.Status.APPROVED,is_archived=False).count()+request.organization.quotes.filter(status=Quote.Status.APPROVED,is_archived=False).count()})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
@require_POST
def delivery_delete(request,delivery_id):
    delivery=get_object_or_404(request.organization.email_deliveries,pk=delivery_id,is_archived=False); delivery.is_archived=True; delivery.archived_at=timezone.now(); delivery.archived_by=request.user; delivery.save(update_fields=['is_archived','archived_at','archived_by']); audit(request,'email_delivery.archived',delivery,{'document_type':delivery.document_type,'document_id':str(delivery.document_id),'recipient':delivery.recipient,'status':delivery.status}); messages.success(request,'De verzendregel is uit het overzicht verwijderd.'); return redirect('outbox')

def parse_day(value):
    try: return date_cls.fromisoformat(value)
    except (TypeError,ValueError): return timezone.localdate()

@login_required
def calendar_view(request):
    mode=request.GET.get('weergave','month'); focus=parse_day(request.GET.get('datum')); member_id=request.GET.get('medewerker','')
    if mode=='day': days=[focus]; previous=focus-timedelta(days=1); following=focus+timedelta(days=1)
    elif mode=='week':
        first=focus-timedelta(days=focus.weekday()); days=[first+timedelta(days=x) for x in range(7)]; previous=focus-timedelta(days=7); following=focus+timedelta(days=7)
    else:
        mode='month'; weeks=calendar.Calendar(firstweekday=0).monthdatescalendar(focus.year,focus.month); days=[d for w in weeks for d in w]; previous=(focus.replace(day=1)-timedelta(days=1)).replace(day=1); following=(focus.replace(day=28)+timedelta(days=7)).replace(day=1)
    start=timezone.make_aware(datetime.combine(days[0],datetime.min.time())); end=timezone.make_aware(datetime.combine(days[-1]+timedelta(days=1),datetime.min.time())); qs=request.organization.appointments.filter(start__lt=end,end__gt=start,is_cancelled=False).select_related('appointment_type','customer').prefetch_related('participants__user')
    if member_id: qs=qs.filter(participants__id=member_id)
    by_day={d:[] for d in days}
    for item in qs:
        local=timezone.localtime(item.start).date()
        if local in by_day: by_day[local].append(item)
    cells=[{'date':d,'events':by_day[d],'current_month':d.month==focus.month,'today':d==timezone.localdate()} for d in days]
    return render(request,'core/calendar.html',{'mode':mode,'focus':focus,'cells':cells,'previous':previous,'following':following,'members':request.organization.memberships.filter(is_active=True).select_related('user'),'member_id':member_id})

def add_month(value):
    year=value.year+(value.month//12); month=value.month%12+1; day=min(value.day,calendar.monthrange(year,month)[1]); return value.replace(year=year,month=month,day=day)

def generate_recurrences(appointment):
    if appointment.recurrence==Appointment.Recurrence.NONE or not appointment.recurrence_until: return 0
    current_start=appointment.start; current_end=appointment.end; participants=list(appointment.participants.all()); count=0
    while count<99:
        if appointment.recurrence==Appointment.Recurrence.DAILY: next_start=current_start+timedelta(days=1); next_end=current_end+timedelta(days=1)
        elif appointment.recurrence==Appointment.Recurrence.WEEKLY: next_start=current_start+timedelta(days=7); next_end=current_end+timedelta(days=7)
        else: next_start=add_month(current_start); next_end=add_month(current_end)
        if timezone.localtime(next_start).date()>appointment.recurrence_until: break
        clone=Appointment.objects.create(organization=appointment.organization,title=appointment.title,appointment_type=appointment.appointment_type,customer=appointment.customer,start=next_start,end=next_end,all_day=appointment.all_day,location=appointment.location,description=appointment.description,reminder_minutes=appointment.reminder_minutes,recurrence=Appointment.Recurrence.NONE,series_id=appointment.series_id,created_by=appointment.created_by); clone.participants.set(participants); current_start,next_start=next_start,current_start; current_end,next_end=next_end,current_end; count+=1
    return count

def appointment_conflicts(org,start,end,participants,exclude=None):
    qs=org.appointments.filter(is_cancelled=False,start__lt=end,end__gt=start,participants__in=participants).exclude(pk=exclude).select_related('appointment_type').distinct(); return list(qs[:10])

@login_required
def appointment_create(request):
    selected=parse_day(request.GET.get('datum')); start=timezone.make_aware(datetime.combine(selected,datetime.min.time().replace(hour=9))); initial={'start':timezone.localtime(start).strftime('%Y-%m-%dT%H:%M'),'end':timezone.localtime(start+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'participants':[request.membership]}; form=AppointmentForm(request.POST or None,initial=initial,organization=request.organization)
    conflicts=[]
    if request.method=='POST' and form.is_valid():
        conflicts=appointment_conflicts(request.organization,form.cleaned_data['start'],form.cleaned_data['end'],form.cleaned_data['participants'])
        if conflicts and request.POST.get('confirm_conflict')!='1': return render(request,'core/appointment_form.html',{'form':form,'conflicts':conflicts,'heading':'Nieuwe afspraak'})
        with transaction.atomic(): appointment=form.save(False); appointment.organization=request.organization; appointment.created_by=request.user; appointment.save(); form.save_m2m(); generated=generate_recurrences(appointment)
        audit(request,'appointment.created',appointment,{'recurrences':generated}); messages.success(request,f'Afspraak opgeslagen{f" met {generated} herhalingen" if generated else ""}.'); return redirect(f"{reverse('calendar')}?datum={timezone.localtime(appointment.start).date()}")
    return render(request,'core/appointment_form.html',{'form':form,'conflicts':conflicts,'heading':'Nieuwe afspraak'})

@login_required
def appointment_detail(request,appointment_id):
    item=get_object_or_404(request.organization.appointments.select_related('customer','appointment_type','created_by').prefetch_related('participants__user'),pk=appointment_id); return render(request,'core/appointment_detail.html',{'item':item})

@login_required
def appointment_edit(request,appointment_id):
    item=get_object_or_404(request.organization.appointments,pk=appointment_id,is_cancelled=False); form=AppointmentForm(request.POST or None,instance=item,organization=request.organization); conflicts=[]
    if request.method=='POST' and form.is_valid():
        conflicts=appointment_conflicts(request.organization,form.cleaned_data['start'],form.cleaned_data['end'],form.cleaned_data['participants'],item.id)
        if conflicts and request.POST.get('confirm_conflict')!='1': return render(request,'core/appointment_form.html',{'form':form,'conflicts':conflicts,'heading':'Afspraak bewerken','item':item})
        form.save(); audit(request,'appointment.updated',item); messages.success(request,'Afspraak bijgewerkt.'); return redirect('appointment_detail',item.id)
    return render(request,'core/appointment_form.html',{'form':form,'conflicts':conflicts,'heading':'Afspraak bewerken','item':item})

@login_required
@require_POST
def appointment_cancel(request,appointment_id):
    item=get_object_or_404(request.organization.appointments,pk=appointment_id); item.is_cancelled=True; item.save(update_fields=['is_cancelled','updated_at']); audit(request,'appointment.cancelled',item); messages.success(request,'Afspraak geannuleerd.'); return redirect('calendar')

@login_required
@owner_required
def team(request):
    members=request.organization.memberships.filter(is_removed=False).select_related('user').order_by('user__display_name')
    return render(request,'core/team.html',{'members':members})

@login_required
@owner_required
@require_POST
def team_reset_two_factor(request,membership_id):
    membership=get_object_or_404(Membership.objects.select_related('user'),pk=membership_id,organization=request.organization,is_removed=False)
    if membership.user_id==request.user.id:
        messages.error(request,'Beheer je eigen tweestapsverificatie via je persoonlijke instellingen.'); return redirect('team')
    membership.user.totp_enabled=False; membership.user.totp_secret_encrypted=''; membership.user.recovery_code_hashes=[]; membership.user.save(update_fields=['totp_enabled','totp_secret_encrypted','recovery_code_hashes'])
    audit(request,'auth.2fa_admin_reset',membership,{'user':membership.user.email}); messages.success(request,f'Tweestapsverificatie van {membership.user.display_name} is gereset.'); return redirect('team')

@login_required
def opportunity_list(request):
    return render(request,'core/opportunity_list.html',{'opportunities':request.organization.opportunities.select_related('customer','owner__user'),'stages':Opportunity.Stage.choices})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.SALES,Membership.Role.CUSTOMER_MANAGER)
def opportunity_form(request,opportunity_id=None):
    opportunity=get_object_or_404(request.organization.opportunities,pk=opportunity_id) if opportunity_id else None; form=OpportunityForm(request.POST or None,instance=opportunity,organization=request.organization)
    if request.method=='POST' and form.is_valid(): obj=form.save(); audit(request,'opportunity.updated' if opportunity else 'opportunity.created',obj); messages.success(request,'Verkoopkans opgeslagen.'); return redirect('opportunity_list')
    return render(request,'core/generic_form.html',{'form':form,'heading':'Verkoopkans bewerken' if opportunity else 'Nieuwe verkoopkans','cancel_url':reverse('opportunity_list')})

@login_required
def project_list(request):
    return render(request,'core/project_list.html',{'projects':request.organization.projects.select_related('customer').prefetch_related('members__user')})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.PROJECT_MANAGER)
def project_form(request,project_id=None):
    project=get_object_or_404(request.organization.projects,pk=project_id) if project_id else None; form=ProjectForm(request.POST or None,instance=project,organization=request.organization)
    if request.method=='POST' and form.is_valid(): obj=form.save(); audit(request,'project.updated' if project else 'project.created',obj); messages.success(request,'Project opgeslagen.'); return redirect('project_detail',obj.id)
    return render(request,'core/generic_form.html',{'form':form,'heading':'Project bewerken' if project else 'Nieuw project','cancel_url':reverse('project_list')})

def scoped_project(request,project_id): return get_object_or_404(request.organization.projects.select_related('customer').prefetch_related('members__user','time_entries__member__user','mileage_entries__member__user','expenses__member__user','documents'),pk=project_id)

@login_required
def project_detail(request,project_id):
    project=scoped_project(request,project_id); return render(request,'core/project_detail.html',{'project':project,'time_form':TimeEntryForm(initial={'date':timezone.localdate()}),'mileage_form':MileageEntryForm(initial={'date':timezone.localdate()}),'expense_form':ExpenseForm(initial={'date':timezone.localdate()}),'document_form':ProjectDocumentForm()})

@login_required
@require_POST
def time_entry_add(request,project_id):
    project=scoped_project(request,project_id); form=TimeEntryForm(request.POST)
    if form.is_valid(): obj=form.save(False); obj.project=project; obj.member=request.membership; obj.save(); audit(request,'time_entry.created',obj); messages.success(request,'Uren opgeslagen.')
    else: messages.error(request,'Controleer de urenregistratie.')
    return redirect('project_detail',project.id)

@login_required
@require_POST
def time_entry_submit(request,entry_id):
    entry=get_object_or_404(request.organization.time_entries,pk=entry_id,member=request.membership,status__in=[TimeEntry.Status.DRAFT,TimeEntry.Status.REJECTED]); entry.status=TimeEntry.Status.SUBMITTED; entry.save(update_fields=['status']); audit(request,'time_entry.submitted',entry); return redirect('project_detail',entry.project_id)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.PROJECT_MANAGER)
@require_POST
def time_entry_approve(request,entry_id):
    entry=get_object_or_404(request.organization.time_entries,pk=entry_id,status=TimeEntry.Status.SUBMITTED); entry.status=TimeEntry.Status.APPROVED; entry.approved_by=request.user; entry.save(update_fields=['status','approved_by']); audit(request,'time_entry.approved',entry); return redirect('project_detail',entry.project_id)

@login_required
@require_POST
def mileage_add(request,project_id):
    project=scoped_project(request,project_id); form=MileageEntryForm(request.POST)
    if form.is_valid(): obj=form.save(False); obj.project=project; obj.member=request.membership; obj.save(); audit(request,'mileage.created',obj); messages.success(request,'Kilometers opgeslagen.')
    else: messages.error(request,'Controleer de kilometerregistratie.')
    return redirect('project_detail',project.id)

@login_required
@require_POST
def expense_add(request,project_id):
    project=scoped_project(request,project_id); form=ExpenseForm(request.POST,request.FILES)
    if form.is_valid(): obj=form.save(False); obj.project=project; obj.member=request.membership; obj.save(); audit(request,'expense.created',obj); messages.success(request,'Onkosten opgeslagen.')
    else: messages.error(request,'Controleer de onkostenregistratie.')
    return redirect('project_detail',project.id)

@login_required
def expense_receipt(request,expense_id):
    obj=get_object_or_404(request.organization.expenses,pk=expense_id); return FileResponse(obj.receipt.open('rb'),as_attachment=True,filename=obj.receipt.name.rsplit('/',1)[-1]) if obj.receipt else HttpResponse(status=404)

@login_required
@require_POST
def project_document_add(request,project_id):
    project=scoped_project(request,project_id); form=ProjectDocumentForm(request.POST,request.FILES)
    if form.is_valid(): obj=form.save(False); obj.organization=request.organization; obj.project=project; obj.customer=project.customer; obj.uploaded_by=request.user; obj.original_name=obj.file.name; obj.content_type=obj.file.content_type or ''; obj.size=obj.file.size; obj.save(); audit(request,'project.document_added',obj); messages.success(request,'Document toegevoegd.')
    else: messages.error(request,'Controleer het document.')
    return redirect('project_detail',project.id)

@login_required
def project_document_download(request,document_id):
    obj=get_object_or_404(request.organization.documents,pk=document_id); audit(request,'project.document_downloaded',obj); return FileResponse(obj.file.open('rb'),as_attachment=True,filename=obj.original_name)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
@require_POST
def project_invoice_time(request,project_id):
    project=scoped_project(request,project_id); entries=project.time_entries.filter(status=TimeEntry.Status.APPROVED,invoice__isnull=True)
    if not entries.exists(): messages.error(request,'Er zijn geen goedgekeurde uren om te factureren.'); return redirect('project_detail',project.id)
    today=timezone.localdate()
    with transaction.atomic():
        invoice=Invoice.objects.create(organization=request.organization,customer=project.customer,created_by=request.user,title=f'Uren {project.name}',issue_date=today,delivery_date=today,due_date=today+timedelta(days=project.customer.payment_term_days),notes=request.organization.default_invoice_notes)
        for position,entry in enumerate(entries.select_for_update(),1): InvoiceLine.objects.create(organization=request.organization,invoice=invoice,position=position,description=f'{entry.date:%d-%m-%Y} · {entry.description}',quantity=entry.hours,unit='uur',unit_price=entry.hourly_rate,vat_rate=21); entry.invoice=invoice; entry.status=TimeEntry.Status.INVOICED; entry.save(update_fields=['invoice','status'])
    audit(request,'invoice.created_from_time',invoice,{'project':str(project.id)}); return redirect('invoice_detail',invoice.id)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def recurring_list(request):
    return render(request,'core/recurring_list.html',{'schedules':request.organization.recurring_invoice_schedules.select_related('customer')})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def recurring_form(request,schedule_id=None):
    schedule=get_object_or_404(request.organization.recurring_invoice_schedules,pk=schedule_id) if schedule_id else None; form=RecurringInvoiceScheduleForm(request.POST or None,instance=schedule,organization=request.organization)
    if request.method=='POST' and form.is_valid(): obj=form.save(False); obj.created_by=schedule.created_by if schedule else request.user; obj.save(); audit(request,'recurring_invoice.updated' if schedule else 'recurring_invoice.created',obj); messages.success(request,'Factuurschema opgeslagen.'); return redirect('recurring_list')
    return render(request,'core/generic_form.html',{'form':form,'heading':'Factuurschema bewerken' if schedule else 'Nieuw factuurschema','cancel_url':reverse('recurring_list')})

@login_required
@owner_required
def reminder_settings(request):
    policy,_=ReminderPolicy.objects.get_or_create(organization=request.organization); form=ReminderPolicyForm(request.POST or None,instance=policy)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'reminder.settings_updated',policy); messages.success(request,'Herinneringsbeleid opgeslagen.'); return redirect('reminder_settings')
    return render(request,'core/reminder_settings.html',{'form':form,'templates':request.organization.email_templates.all(),'kinds':EmailTemplate.Kind.choices})

@login_required
@owner_required
def email_template_edit(request,kind):
    if kind not in EmailTemplate.Kind.values: raise Http404
    defaults={'subject':f'ToolMigo CRM · {EmailTemplate.Kind(kind).label}','body':'Beste {{ klantnaam }},\n\nDocument {{ factuurnummer }} heeft een openstaand bedrag van € {{ bedrag }}.'}; template,_=EmailTemplate.objects.get_or_create(organization=request.organization,kind=kind,defaults=defaults); form=EmailTemplateForm(request.POST or None,instance=template)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'email_template.updated',template,{'kind':kind}); messages.success(request,'E-mailsjabloon opgeslagen.'); return redirect('reminder_settings')
    preview=(form['body'].value() or '').replace('{{ klantnaam }}','Voorbeeldklant').replace('{{ factuurnummer }}','FAC-2026-0001').replace('{{ bedrag }}','1.250,00').replace('{{ vervaldatum }}','30-09-2026')
    return render(request,'core/email_template_form.html',{'form':form,'template':template,'preview':preview})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def reminder_list(request):
    return render(request,'core/reminder_list.html',{'reminders':request.organization.payment_reminders.select_related('invoice','invoice__customer')})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
@require_POST
def reminder_send(request,reminder_id):
    reminder=get_object_or_404(request.organization.payment_reminders,pk=reminder_id,status__in=[PaymentReminder.Status.QUEUED,PaymentReminder.Status.FAILED])
    try:
        config,connection=organization_mail_connection(request.organization); EmailMessage(reminder.subject,reminder.body,config.from_email,[reminder.recipient],connection=connection).send(fail_silently=False); reminder.status=PaymentReminder.Status.SENT; reminder.sent_at=timezone.now(); reminder.error=''; messages.success(request,'Herinnering verzonden.')
    except Exception as exc: reminder.status=PaymentReminder.Status.FAILED; reminder.error=str(exc)[:1000]; messages.error(request,'Herinnering kon niet worden verzonden.')
    reminder.save(update_fields=['status','sent_at','error']); audit(request,'reminder.send_attempt',reminder,{'status':reminder.status}); return redirect('reminder_list')

def csv_bytes(rows):
    output=io.StringIO(); writer=csv.writer(output,lineterminator='\n'); writer.writerows(rows); return output.getvalue().encode('utf-8-sig')

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def bookkeeping_export(request):
    start_text=request.GET.get('start',''); end_text=request.GET.get('end','')
    if not start_text or not end_text: return render(request,'core/bookkeeping_export.html',{'start':start_text,'end':end_text})
    try: start=date_cls.fromisoformat(start_text); end=date_cls.fromisoformat(end_text)
    except ValueError: messages.error(request,'Kies geldige datums.'); return redirect('bookkeeping_export')
    if end<start or (end-start).days>366: messages.error(request,'De exportperiode moet oplopen en maximaal 366 dagen zijn.'); return redirect('bookkeeping_export')
    invoices=request.organization.invoices.filter(issue_date__range=[start,end],is_archived=False).select_related('customer').prefetch_related('lines','payments').order_by('issue_date','number')
    invoice_rows=[['nummer','datum','klant','excl_btw','btw','incl_btw','betaald','openstaand','status']]; line_rows=[['factuur','omschrijving','aantal','prijs','btw_percentage','netto','btw_bedrag']]; payment_rows=[['factuur','betaaldatum','bedrag','referentie']]
    for invoice in invoices:
        invoice_rows.append([invoice.number,invoice.issue_date,str(invoice.customer),invoice.subtotal,invoice.vat_total,invoice.total,invoice.paid_amount,invoice.outstanding,invoice.status])
        for line in invoice.lines.all(): line_rows.append([invoice.number,line.description,line.quantity,line.unit_price,line.vat_rate,line.net_amount,line.vat_amount])
        for payment in invoice.payments.all(): payment_rows.append([invoice.number,payment.paid_on,payment.amount,payment.reference])
    files={'facturen.csv':csv_bytes(invoice_rows),'regels.csv':csv_bytes(line_rows),'betalingen.csv':csv_bytes(payment_rows)}; manifest={'organization':str(request.organization.id),'period':{'start':start_text,'end':end_text},'generated_at':timezone.now().isoformat(),'counts':{'invoices':len(invoice_rows)-1,'lines':len(line_rows)-1,'payments':len(payment_rows)-1},'sha256':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}; files['controle.json']=json.dumps(manifest,indent=2).encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items(): archive.writestr(name,data)
    audit(request,'bookkeeping.exported',metadata={'start':start_text,'end':end_text,'counts':manifest['counts']}); response=HttpResponse(output.getvalue(),content_type='application/zip'); response['Content-Disposition']=f'attachment; filename="boekhouding-{start_text}-{end_text}.zip"'; return response

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.CUSTOMER_MANAGER)
def portal_manage(request,customer_id):
    customer=get_object_or_404(request.organization.customers,pk=customer_id)
    if request.method=='POST':
        contact=get_object_or_404(customer.contacts,pk=request.POST.get('contact'),is_active=True)
        try: days=max(1,min(90,int(request.POST.get('days','14'))))
        except ValueError: days=14
        token=secrets.token_urlsafe(32); access=PortalAccess.objects.create(organization=request.organization,customer=customer,contact=contact,token_digest=hashlib.sha256(token.encode()).hexdigest(),token_hint=token[-8:],expires_at=timezone.now()+timedelta(days=days),created_by=request.user); request.session['new_portal_link']=request.build_absolute_uri(reverse('portal_token',args=[token])); audit(request,'portal.access_created',access,{'contact':str(contact),'expires_at':access.expires_at.isoformat()}); return redirect('portal_manage',customer.id)
    link=request.session.pop('new_portal_link',None); return render(request,'core/portal_manage.html',{'customer':customer,'contacts':customer.contacts.filter(is_active=True),'accesses':customer.portal_accesses.select_related('contact'),'new_link':link})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.CUSTOMER_MANAGER)
@require_POST
def portal_revoke(request,access_id):
    access=get_object_or_404(request.organization.portal_accesses,pk=access_id); access.revoked_at=timezone.now(); access.save(update_fields=['revoked_at']); audit(request,'portal.access_revoked',access); messages.success(request,'Portaaltoegang is ingetrokken.'); return redirect('portal_manage',access.customer_id)

def portal_token(request,token):
    digest=hashlib.sha256(token.encode()).hexdigest(); access=PortalAccess.objects.filter(token_digest=digest,revoked_at__isnull=True,expires_at__gt=timezone.now(),customer__status__in=[Customer.Status.ACTIVE,Customer.Status.INACTIVE]).first()
    if not access: return render(request,'core/portal_invalid.html',status=403)
    request.session.cycle_key(); request.session['portal_access_id']=str(access.id); access.last_used_at=timezone.now(); access.save(update_fields=['last_used_at']); return redirect('portal_home')

def current_portal_access(request):
    value=request.session.get('portal_access_id')
    if not value: return None
    return PortalAccess.objects.select_related('organization','customer','contact').filter(pk=value,revoked_at__isnull=True,expires_at__gt=timezone.now()).first()

def portal_home(request):
    access=current_portal_access(request)
    if not access: return redirect('portal_invalid')
    customer=access.customer; quotes=customer.quotes.filter(is_archived=False,status__in=[Quote.Status.APPROVED,Quote.Status.SENT,Quote.Status.ACCEPTED,Quote.Status.DECLINED]); invoices=customer.invoices.filter(is_archived=False,status__in=[Invoice.Status.APPROVED,Invoice.Status.QUEUED,Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.PAID,Invoice.Status.OVERDUE]); documents=customer.documents.filter(visible_to_portal=True)
    return render(request,'core/portal_home.html',{'access':access,'quotes':quotes,'invoices':invoices,'documents':documents})

def portal_invalid(request): return render(request,'core/portal_invalid.html',status=403)

@require_POST
def portal_logout(request): request.session.pop('portal_access_id',None); return redirect('portal_invalid')

def portal_quote_pdf(request,quote_id):
    access=current_portal_access(request)
    if not access: return redirect('portal_invalid')
    quote=get_object_or_404(access.customer.quotes.filter(is_archived=False),pk=quote_id,status__in=[Quote.Status.APPROVED,Quote.Status.SENT,Quote.Status.ACCEPTED,Quote.Status.DECLINED]); return FileResponse(io.BytesIO(build_quote_pdf(quote)),content_type='application/pdf',as_attachment=True,filename=f'offerte-{quote.number}.pdf')

def portal_invoice_pdf(request,invoice_id):
    access=current_portal_access(request)
    if not access: return redirect('portal_invalid')
    invoice=get_object_or_404(access.customer.invoices.filter(is_archived=False),pk=invoice_id,status__in=[Invoice.Status.APPROVED,Invoice.Status.QUEUED,Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.PAID,Invoice.Status.OVERDUE]); return FileResponse(io.BytesIO(build_invoice_pdf(invoice)),content_type='application/pdf',as_attachment=True,filename=f'factuur-{invoice.number}.pdf')

@require_POST
def portal_quote_decide(request,quote_id):
    access=current_portal_access(request)
    if not access: return redirect('portal_invalid')
    quote=get_object_or_404(access.customer.quotes.filter(is_archived=False),pk=quote_id,status__in=[Quote.Status.APPROVED,Quote.Status.SENT])
    decision=request.POST.get('decision'); signer=request.POST.get('signer_name','').strip(); reason=request.POST.get('reason','').strip()
    if decision not in PortalDecision.Decision.values or len(signer)<2: messages.error(request,'Vul je naam in en kies accepteren of afwijzen.'); return redirect('portal_home')
    pdf=build_quote_pdf(quote)
    with transaction.atomic():
        PortalDecision.objects.create(organization=access.organization,portal_access=access,quote=quote,decision=decision,signer_name=signer,reason=reason,document_sha256=hashlib.sha256(pdf).hexdigest(),ip_address=request.META.get('HTTP_X_FORWARDED_FOR',request.META.get('REMOTE_ADDR','')).split(',')[0].strip() or None); quote.status=Quote.Status.ACCEPTED if decision==PortalDecision.Decision.ACCEPTED else Quote.Status.DECLINED; quote.save(update_fields=['status','updated_at'])
    AuditEvent.objects.create(organization=access.organization,action=f'portal.quote_{decision}',target_type='Quote',target_id=str(quote.id),metadata={'signer':signer,'document_sha256':hashlib.sha256(pdf).hexdigest()}); messages.success(request,'Je keuze is veilig geregistreerd.'); return redirect('portal_home')

def portal_document_download(request,document_id):
    access=current_portal_access(request)
    if not access: return redirect('portal_invalid')
    document=get_object_or_404(access.customer.documents,pk=document_id,visible_to_portal=True); return FileResponse(document.file.open('rb'),as_attachment=True,filename=document.original_name)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def reports(request):
    org=request.organization; start_text=request.GET.get('start',''); end_text=request.GET.get('end','')
    try: end=date_cls.fromisoformat(end_text) if end_text else timezone.localdate(); start=date_cls.fromisoformat(start_text) if start_text else end-timedelta(days=365)
    except ValueError: messages.error(request,'Kies geldige rapportdatums.'); return redirect('reports')
    if end<start or (end-start).days>3660: messages.error(request,'Kies een geldige periode van maximaal tien jaar.'); return redirect('reports')
    invoices=org.invoices.filter(is_archived=False,issue_date__range=[start,end]).select_related('customer').prefetch_related('lines','payments'); revenue=sum((x.subtotal for x in invoices if x.status not in [Invoice.Status.DRAFT,Invoice.Status.REJECTED]),Decimal('0')); vat=sum((x.vat_total for x in invoices if x.status not in [Invoice.Status.DRAFT,Invoice.Status.REJECTED]),Decimal('0')); outstanding=sum((x.outstanding for x in invoices if x.status in [Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.OVERDUE]),Decimal('0'))
    pipeline=[]
    for value,label in Opportunity.Stage.choices:
        items=org.opportunities.filter(stage=value); pipeline.append({'label':label,'count':items.count(),'value':sum((x.expected_revenue*Decimal(x.probability)/100 for x in items),Decimal('0'))})
    project_rows=[]
    for project in org.projects.all().prefetch_related('time_entries','expenses','mileage_entries'):
        hours=sum((x.hours for x in project.time_entries.all()),Decimal('0')); labor=sum((x.amount for x in project.time_entries.all()),Decimal('0')); expenses=sum((x.amount for x in project.expenses.all()),Decimal('0'))+sum((x.amount for x in project.mileage_entries.all()),Decimal('0')); project_rows.append({'project':project,'hours':hours,'labor':labor,'expenses':expenses,'margin':project.budget-labor-expenses})
    return render(request,'core/reports.html',{'start':start,'end':end,'revenue':revenue,'vat':vat,'outstanding':outstanding,'pipeline':pipeline,'projects':project_rows})

@login_required
@owner_required
def system_info(request):
    return render(request,'core/system_info.html',{'update_available':settings.AVAILABLE_VERSION!=settings.APP_VERSION})

@login_required
@owner_required
def team_add(request):
    form=TeamMemberForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            user=form.save(commit=False); user.email=user.email.lower(); user.save()
            membership=Membership.objects.create(organization=request.organization,user=user,role=form.cleaned_data['role'])
            audit(request,'team.member_created',membership,{'email':user.email,'role':membership.role})
        messages.success(request,f'{user.display_name} is toegevoegd aan het team.')
        return redirect('team')
    return render(request,'core/team_form.html',{'form':form})

@login_required
@owner_required
def team_edit(request,membership_id):
    membership=get_object_or_404(Membership.objects.select_related('user'),pk=membership_id,organization=request.organization,is_removed=False)
    form=TeamMemberEditForm(request.POST or None,instance=membership.user,membership=membership)
    if request.method=='POST' and form.is_valid():
        new_role=form.cleaned_data['role']
        if membership.user_id==request.user.id and new_role!=Membership.Role.OWNER:
            form.add_error('role','Je kunt je eigen rol als bedrijfsbeheerder niet wijzigen.')
        else:
            with transaction.atomic():
                user=form.save(); old_role=membership.role; membership.role=new_role; membership.save(update_fields=['role'])
                audit(request,'team.member_updated',membership,{'email':user.email,'old_role':old_role,'new_role':new_role})
            messages.success(request,f'Het account van {user.display_name} is bijgewerkt.')
            return redirect('team')
    return render(request,'core/team_form.html',{'form':form,'editing':True,'member':membership})

@login_required
@owner_required
@require_POST
def team_remove(request,membership_id):
    membership=get_object_or_404(Membership.objects.select_related('user'),pk=membership_id,organization=request.organization,is_removed=False)
    if membership.user_id==request.user.id:
        messages.error(request,'Je kunt je eigen account niet verwijderen.')
    else:
        with transaction.atomic():
            membership.is_active=False; membership.is_removed=True; membership.removed_at=timezone.now(); membership.removed_by=request.user
            membership.save(update_fields=['is_active','is_removed','removed_at','removed_by'])
            if not membership.user.memberships.filter(is_active=True,is_removed=False,organization__is_active=True).exists():
                membership.user.is_active=False; membership.user.save(update_fields=['is_active'])
            audit(request,'team.member_removed',membership,{'email':membership.user.email,'role':membership.role})
        messages.success(request,f'{membership.user.display_name} is verwijderd en heeft geen toegang meer tot deze organisatie.')
    return redirect('team')

@login_required
@owner_required
@require_POST
def team_toggle(request,membership_id):
    membership=get_object_or_404(Membership,pk=membership_id,organization=request.organization,is_removed=False)
    if membership.user_id==request.user.id:
        messages.error(request,'Je kunt je eigen lidmaatschap niet uitschakelen.')
    else:
        membership.is_active=not membership.is_active; membership.save(update_fields=['is_active'])
        audit(request,'team.member_status_changed',membership,{'active':membership.is_active})
        messages.success(request,'De teamstatus is aangepast.')
    return redirect('team')

def ensure_default_board(organization):
    board=organization.boards.filter(is_archived=False).order_by('-is_default','created_at').first()
    if board: return board
    with transaction.atomic():
        board=Board.objects.create(organization=organization,name='Werkbord',is_default=True)
        for position,(name,color,done) in enumerate([('Inbox','#64748B',False),('Gepland','#2563EB',False),('Bezig','#F59E0B',False),('Wachten','#8B5CF6',False),('Afgerond','#239F7F',True)],1): BoardColumn.objects.create(board=board,name=name,color=color,position=position,is_done=done)
    return board

@login_required
def board_list(request):
    board=ensure_default_board(request.organization)
    boards=request.organization.boards.filter(is_archived=False).annotate(task_count=Count('tasks',filter=Q(tasks__is_archived=False)))
    return render(request,'core/board_list.html',{'boards':boards,'default_board':board})

@login_required
def board_detail(request,board_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False)
    mine=request.GET.get('mine')=='1'; overdue=request.GET.get('overdue')=='1'; query=request.GET.get('q','').strip()
    tasks=Task.objects.filter(organization=request.organization,board=board,is_archived=False).select_related('customer','column').prefetch_related('assignees__user','checklist')
    if mine: tasks=tasks.filter(assignees=request.membership)
    if overdue: tasks=tasks.filter(due_date__lt=timezone.now(),completed_at__isnull=True)
    if query: tasks=tasks.filter(Q(title__icontains=query)|Q(description__icontains=query)|Q(customer__legal_name__icontains=query)).distinct()
    grouped={str(column.id):[] for column in board.columns.all()}
    for task in tasks: grouped.setdefault(str(task.column_id),[]).append(task)
    columns=[{'column':column,'tasks':grouped.get(str(column.id),[])} for column in board.columns.all()]
    return render(request,'core/board_detail.html',{'board':board,'columns':columns,'boards':request.organization.boards.filter(is_archived=False),'mine':mine,'overdue':overdue,'query':query,'now':timezone.now()})

@login_required
@owner_required
def board_create(request):
    form=BoardForm(request.POST or None,organization=request.organization)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            board=form.save()
            if board.is_default: request.organization.boards.exclude(pk=board.pk).update(is_default=False)
            for position,(name,color,done) in enumerate([('Inbox','#64748B',False),('Gepland','#2563EB',False),('Bezig','#F59E0B',False),('Afgerond','#239F7F',True)],1): BoardColumn.objects.create(board=board,name=name,color=color,position=position,is_done=done)
        audit(request,'board.created',board); messages.success(request,'Het bord is aangemaakt.'); return redirect('board_detail',board.id)
    return render(request,'core/board_form.html',{'form':form,'heading':'Nieuw bord'})

@login_required
@owner_required
def column_add(request,board_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False); form=BoardColumnForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        column=form.save(False); column.board=board; column.position=(board.columns.aggregate(max=Count('id'))['max'] or 0)+1; column.save(); audit(request,'board.column_created',column); messages.success(request,'Kolom toegevoegd.'); return redirect('board_detail',board.id)
    return render(request,'core/board_form.html',{'form':form,'heading':'Kolom toevoegen','board':board})

@login_required
@owner_required
def column_edit(request,board_id,column_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False); column=get_object_or_404(board.columns,pk=column_id); form=BoardColumnForm(request.POST or None,instance=column)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'board.column_updated',column); messages.success(request,'Kolom bijgewerkt.'); return redirect('board_detail',board.id)
    return render(request,'core/board_form.html',{'form':form,'heading':'Kolom bewerken','board':board})

@login_required
def task_create(request,board_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False); first=board.columns.first()
    if not first: messages.error(request,'Voeg eerst een kolom toe.'); return redirect('board_detail',board.id)
    form=TaskForm(request.POST or None,organization=request.organization,board=board,initial={'assignees':[request.membership]})
    if request.method=='POST' and form.is_valid():
        task=form.save(False); task.column=first; task.created_by=request.user; task.position=first.tasks.filter(is_archived=False).count()+1; task.save(); form.save_m2m(); audit(request,'task.created',task); messages.success(request,'Taak aangemaakt.'); return redirect('task_detail',board.id,task.id)
    return render(request,'core/task_form.html',{'form':form,'board':board,'heading':'Nieuwe taak'})

@login_required
def task_detail(request,board_id,task_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False); task=get_object_or_404(Task.objects.select_related('customer','quote','invoice','appointment','created_by','column').prefetch_related('assignees__user','checklist','comments__author','attachments'),pk=task_id,organization=request.organization,board=board,is_archived=False)
    return render(request,'core/task_detail.html',{'board':board,'task':task,'comment_form':TaskCommentForm(),'checklist_form':ChecklistItemForm(),'attachment_form':TaskAttachmentForm()})

@login_required
def task_edit(request,board_id,task_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False); task=get_object_or_404(Task,pk=task_id,organization=request.organization,board=board,is_archived=False); form=TaskForm(request.POST or None,instance=task,organization=request.organization,board=board)
    if request.method=='POST' and form.is_valid(): form.save(); audit(request,'task.updated',task); messages.success(request,'Taak bijgewerkt.'); return redirect('task_detail',board.id,task.id)
    return render(request,'core/task_form.html',{'form':form,'board':board,'task':task,'heading':'Taak bewerken'})

@login_required
@require_POST
def task_move(request,board_id,task_id):
    board=get_object_or_404(request.organization.boards,pk=board_id,is_archived=False)
    try: data=json.loads(request.body or '{}'); target_id=data['column_id']; position=max(1,int(data.get('position',1)))
    except (ValueError,TypeError,KeyError,json.JSONDecodeError): return JsonResponse({'error':'Ongeldige verplaatsing.'},status=400)
    with transaction.atomic():
        task=get_object_or_404(Task.objects.select_for_update(),pk=task_id,organization=request.organization,board=board,is_archived=False); target=get_object_or_404(BoardColumn,pk=target_id,organization=request.organization,board=board)
        old=task.column; task.column=target; task.position=position; task.completed_at=timezone.now() if target.is_done else None; task.save(update_fields=['column','position','completed_at','updated_at'])
        for column in {old,target}:
            for index,item in enumerate(column.tasks.filter(is_archived=False).order_by('position','updated_at'),1):
                if item.position!=index: Task.objects.filter(pk=item.pk).update(position=index)
    audit(request,'task.moved',task,{'column':target.name}); return JsonResponse({'ok':True,'completed':bool(task.completed_at)})

@login_required
@require_POST
def checklist_add(request,board_id,task_id):
    task=get_object_or_404(Task,pk=task_id,organization=request.organization,board_id=board_id,is_archived=False); form=ChecklistItemForm(request.POST)
    if form.is_valid(): item=TaskChecklistItem.objects.create(task=task,text=form.cleaned_data['text'],position=task.checklist.count()+1); audit(request,'task.checklist_added',item)
    else: messages.error(request,'Vul een geldig checklistitem in.')
    return redirect('task_detail',board_id,task.id)

@login_required
@require_POST
def checklist_toggle(request,board_id,task_id,item_id):
    item=get_object_or_404(TaskChecklistItem,pk=item_id,task_id=task_id,organization=request.organization,task__board_id=board_id); item.is_done=not item.is_done; item.completed_at=timezone.now() if item.is_done else None; item.save(update_fields=['is_done','completed_at']); audit(request,'task.checklist_toggled',item,{'done':item.is_done}); return redirect('task_detail',board_id,task_id)

@login_required
@require_POST
def task_comment(request,board_id,task_id):
    task=get_object_or_404(Task,pk=task_id,organization=request.organization,board_id=board_id,is_archived=False); form=TaskCommentForm(request.POST)
    if form.is_valid(): comment=TaskComment.objects.create(task=task,author=request.user,body=form.cleaned_data['body']); audit(request,'task.comment_created',comment)
    else: messages.error(request,'De opmerking kon niet worden geplaatst.')
    return redirect('task_detail',board_id,task.id)

@login_required
@require_POST
def task_attachment(request,board_id,task_id):
    task=get_object_or_404(Task,pk=task_id,organization=request.organization,board_id=board_id,is_archived=False); form=TaskAttachmentForm(request.POST,request.FILES)
    if form.is_valid():
        uploaded=form.cleaned_data['file']; attachment=form.save(False); attachment.task=task; attachment.uploaded_by=request.user; attachment.original_name=uploaded.name; attachment.content_type=getattr(uploaded,'content_type',''); attachment.size=uploaded.size; attachment.save(); audit(request,'task.attachment_uploaded',attachment); messages.success(request,'Bijlage toegevoegd.')
    else: messages.error(request,form.errors.get('file',['Bijlage kon niet worden toegevoegd.'])[0])
    return redirect('task_detail',board_id,task.id)

@login_required
def attachment_download(request,board_id,task_id,attachment_id):
    attachment=get_object_or_404(TaskAttachment,pk=attachment_id,task_id=task_id,organization=request.organization,task__board_id=board_id); return FileResponse(attachment.file.open('rb'),as_attachment=True,filename=attachment.original_name,content_type=attachment.content_type or 'application/octet-stream')

@login_required
@require_POST
def task_archive(request,board_id,task_id):
    task=get_object_or_404(Task,pk=task_id,organization=request.organization,board_id=board_id); task.is_archived=True; task.save(update_fields=['is_archived','updated_at']); audit(request,'task.archived',task); messages.success(request,'Taak gearchiveerd.'); return redirect('board_detail',board_id)

@login_required
@require_POST
def logout_view(request):
    audit(request,'auth.logout'); logout(request); return redirect('login')
