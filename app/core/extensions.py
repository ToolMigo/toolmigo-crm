import csv
import hashlib
import hmac
import io
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import base64
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (BankImportForm, CalendarConnectionForm, CommunicationForm, DataImportForm,
                    ContractForm, DocumentTemplateForm, IntegrationEndpointForm,
                    ServiceTicketForm, StockMovementForm, WorkOrderForm)
from .models import (BankTransaction, CalendarConnection, Communication, Contract, Customer,
                     DocumentTemplate, IntegrationEndpoint, Invoice, Membership,
                     Payment, PaymentLink, Product, ServiceTicket, SignatureRequest,
                     StockMovement, SystemAlert, WebhookDelivery, WorkOrder)
from .security import audit, owner_required, roles_required

MANAGER_ROLES=(Membership.Role.OWNER,Membership.Role.BILLING,Membership.Role.SALES,Membership.Role.CUSTOMER_MANAGER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)

def _smtp(org):
    cfg=org.email_settings
    return get_connection(host=cfg.host,port=cfg.port,username=cfg.username,password=cfg.get_password(),use_tls=cfg.use_tls,use_ssl=cfg.use_ssl,fail_silently=False),cfg.from_email

@login_required
def operations_hub(request):
    org=request.organization
    counts={'communications':org.communications.count(),'contracts':org.contracts.count(),'tickets':org.service_tickets.exclude(status__in=['resolved','closed']).count(),'work_orders':org.work_orders.exclude(status__in=['completed','cancelled']).count(),'low_stock':sum(1 for p in org.products.filter(track_stock=True) if p.stock_quantity<=p.minimum_stock),'bank_unmatched':org.bank_transactions.filter(invoice__isnull=True).count(),'alerts':org.system_alerts.filter(is_resolved=False).count()}
    return render(request,'core/operations_hub.html',{'counts':counts})

@login_required
@roles_required(*MANAGER_ROLES)
def communication_list(request): return render(request,'core/communications.html',{'items':request.organization.communications.select_related('customer')[:200]})

@login_required
@roles_required(*MANAGER_ROLES)
def communication_create(request):
    form=CommunicationForm(request.POST or None,organization=request.organization)
    if form.is_valid():
        obj=form.save(False); obj.organization=request.organization; obj.created_by=request.user; obj.sender=getattr(getattr(request.organization,'email_settings',None),'from_email',''); obj.save(); audit(request,'communication.created',obj); return redirect('communication_list')
    return render(request,'core/generic_form.html',{'form':form,'heading':'E-mail opstellen','cancel_url':reverse('communication_list')})

@login_required
@roles_required(*MANAGER_ROLES)
@require_POST
def communication_send(request,communication_id):
    item=get_object_or_404(Communication,pk=communication_id,organization=request.organization,status__in=[Communication.Status.DRAFT,Communication.Status.FAILED])
    try:
        connection,from_email=_smtp(request.organization); EmailMessage(item.subject,item.body,from_email,[item.recipient],connection=connection).send(); item.status=Communication.Status.SENT; item.sent_at=timezone.now(); item.error=''; item.save(update_fields=['status','sent_at','error']); audit(request,'communication.sent',item)
    except Exception as exc:
        item.status=Communication.Status.FAILED; item.error=str(exc)[:1000]; item.save(update_fields=['status','error']); messages.error(request,'Verzenden mislukt; controleer de SMTP-instellingen.')
    return redirect('communication_list')

def _crud(request,model,form_class,title,list_name,pk=None,creator=False):
    obj=get_object_or_404(model,pk=pk,organization=request.organization) if pk else None; form=form_class(request.POST or None,request.FILES or None,instance=obj,organization=request.organization)
    if form.is_valid():
        saved=form.save(False); saved.organization=request.organization
        if creator and not saved.pk: saved.created_by=request.user
        if isinstance(saved,DocumentTemplate) and saved.is_default: DocumentTemplate.objects.filter(organization=request.organization,kind=saved.kind,is_default=True).exclude(pk=saved.pk).update(is_default=False)
        saved.save(); form.save_m2m(); audit(request,f'{model.__name__.lower()}.saved',saved); return redirect(list_name)
    return render(request,'core/generic_form.html',{'form':form,'heading':title,'cancel_url':reverse(list_name)})

@login_required
@roles_required(*MANAGER_ROLES)
def contract_list(request): return render(request,'core/extension_list.html',{'title':'Contracten','eyebrow':'CONTRACTBEHEER','create_url':'contract_create','headers':['Klant','Contract','Status','Start','Einde','Waarde'],'rows':[{'cells':[x.customer,x.title,x.get_status_display(),x.start_date.strftime('%d-%m-%Y'),x.end_date.strftime('%d-%m-%Y') if x.end_date else 'Doorlopend',f'€ {x.value}'],'url':reverse('contract_edit',args=[x.id])} for x in request.organization.contracts.select_related('customer')]})
@login_required
@roles_required(*MANAGER_ROLES)
def contract_form(request,contract_id=None): return _crud(request,Contract,ContractForm,'Contract','contract_list',contract_id)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.CUSTOMER_MANAGER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)
def ticket_list(request): return render(request,'core/extension_list.html',{'title':'Servicetickets','eyebrow':'SERVICE','create_url':'ticket_create','headers':['Klant','Onderwerp','Prioriteit','Status','Behandelaar'],'rows':[{'cells':[x.customer,x.subject,x.get_priority_display(),x.get_status_display(),x.assignee.user.display_name if x.assignee else 'Niet toegewezen'],'url':reverse('ticket_edit',args=[x.id])} for x in request.organization.service_tickets.select_related('customer','assignee__user')]})
@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.CUSTOMER_MANAGER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)
def ticket_form(request,ticket_id=None): return _crud(request,ServiceTicket,ServiceTicketForm,'Serviceticket','ticket_list',ticket_id,creator=True)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.PLANNER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)
def work_order_list(request): return render(request,'core/extension_list.html',{'title':'Routes en werkbonnen','eyebrow':'BUITENDIENST','create_url':'work_order_create','headers':['Tijd','Klant','Werkbon','Adres','Medewerker','Status'],'rows':[{'cells':[x.scheduled_start.strftime('%d-%m-%Y %H:%M'),x.customer,x.title,x.address,x.assigned_to.user.display_name if x.assigned_to else 'Niet toegewezen',x.get_status_display()],'url':reverse('work_order_edit',args=[x.id]),'attachment_url':reverse('work_order_photo',args=[x.id]) if x.photo else ''} for x in request.organization.work_orders.select_related('customer','assigned_to__user')]})
@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.PLANNER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)
def work_order_form(request,work_order_id=None): return _crud(request,WorkOrder,WorkOrderForm,'Werkbon','work_order_list',work_order_id)
@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.PLANNER,Membership.Role.PROJECT_MANAGER,Membership.Role.SUPPORT)
def work_order_photo(request,work_order_id):
    item=get_object_or_404(WorkOrder,pk=work_order_id,organization=request.organization)
    if not item.photo: return JsonResponse({'error':'not_found'},status=404)
    return FileResponse(item.photo.open('rb'),as_attachment=True,filename=item.photo.name.rsplit('/',1)[-1])

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def inventory(request): return render(request,'core/inventory.html',{'products':request.organization.products.all(),'movements':request.organization.stock_movements.select_related('product')[:100]})
@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def stock_movement(request):
    form=StockMovementForm(request.POST or None,organization=request.organization)
    if form.is_valid():
        with transaction.atomic():
            product=Product.objects.select_for_update().get(pk=form.cleaned_data['product'].pk,organization=request.organization); movement=form.save(False); movement.organization=request.organization; movement.product=product; movement.created_by=request.user; movement.save(); delta=movement.quantity if movement.kind=='in' else -movement.quantity if movement.kind=='out' else movement.quantity; product.stock_quantity+=delta; product.save(update_fields=['stock_quantity'])
        audit(request,'stock.movement',movement); return redirect('inventory')
    return render(request,'core/generic_form.html',{'form':form,'heading':'Voorraadmutatie','cancel_url':reverse('inventory')})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
def bank_import(request):
    form=BankImportForm(request.POST or None,request.FILES or None); result=None
    if form.is_valid():
        text=form.cleaned_data['file'].read().decode('utf-8-sig'); rows=_parse_bank_rows(text); created=matched=0
        for row in rows:
            try: booked=date.fromisoformat(row.get('datum') or row.get('date')); amount=Decimal(str(row.get('bedrag') or row.get('amount')).replace(',','.')); reference=(row.get('omschrijving') or row.get('reference') or '')[:300]
            except (ValueError,InvalidOperation,AttributeError): continue
            digest=hashlib.sha256(f'{booked}|{amount}|{reference}'.encode()).hexdigest(); tx,new=BankTransaction.objects.get_or_create(organization=request.organization,import_hash=digest,defaults={'booking_date':booked,'amount':amount,'reference':reference,'counterparty':row.get('tegenpartij','')[:200],'iban':row.get('iban','')[:34]}); created+=int(new)
            if new and amount>0:
                invoice=next((i for i in request.organization.invoices.exclude(number='').prefetch_related('lines','payments') if i.number.lower() in reference.lower() and i.outstanding==amount),None)
                if invoice: tx.invoice=invoice; tx.matched_at=timezone.now(); tx.save(update_fields=['invoice','matched_at']); Payment.objects.create(organization=request.organization,invoice=invoice,amount=amount,paid_on=booked,reference=f'Bankimport {reference}',recorded_by=request.user); matched+=1
        audit(request,'bank.import',metadata={'created':created,'matched':matched}); result={'created':created,'matched':matched}
    return render(request,'core/bank_import.html',{'form':form,'result':result,'transactions':request.organization.bank_transactions.select_related('invoice')[:100]})

def _parse_bank_rows(text):
    stripped=text.lstrip()
    if stripped.startswith('<'):
        root=ET.fromstring(text); rows=[]
        for entry in [x for x in root.iter() if x.tag.rsplit('}',1)[-1]=='Ntry']:
            def first(name): return next((x.text for x in entry.iter() if x.tag.rsplit('}',1)[-1]==name and x.text), '')
            amount=first('Amt'); indicator=first('CdtDbtInd'); rows.append({'datum':first('Dt') or first('DtTm')[:10],'bedrag':('-' if indicator=='DBIT' else '')+amount,'omschrijving':first('AddtlNtryInf') or first('Ustrd') or first('EndToEndId'),'tegenpartij':first('Nm'),'iban':first('IBAN')})
        return rows
    if ':20:' in text and ':61:' in text:
        rows=[]; current=None
        for line in text.splitlines():
            if line.startswith(':61:'):
                match=re.match(r':61:(\d{6})(?:\d{4})?([CD])([0-9,]+)',line)
                if match:
                    year=2000+int(match.group(1)[:2]); current={'datum':f'{year:04d}-{match.group(1)[2:4]}-{match.group(1)[4:6]}','bedrag':('-' if match.group(2)=='D' else '')+match.group(3),'omschrijving':line[4:]}; rows.append(current)
            elif line.startswith(':86:') and current: current['omschrijving']=line[4:]
        return rows
    return list(csv.DictReader(io.StringIO(text),delimiter=';' if ';' in text.splitlines()[0] else ','))

@login_required
@owner_required
def template_list(request): return render(request,'core/extension_list.html',{'title':'Documentsjablonen','eyebrow':'HUISSTIJL','create_url':'template_create','headers':['Type','Naam','Standaard','Kleur'],'rows':[{'cells':[x.get_kind_display(),x.name,'Ja' if x.is_default else 'Nee',x.primary_color],'url':reverse('template_edit',args=[x.id])} for x in request.organization.document_templates.all()]})
@login_required
@owner_required
def template_form(request,template_id=None):
    obj=get_object_or_404(DocumentTemplate,pk=template_id,organization=request.organization) if template_id else None; initial={'layout_order':','.join(obj.layout or ['header','recipient','lines','totals','terms','footer'])} if obj else {'layout_order':'header,recipient,lines,totals,terms,footer'}; form=DocumentTemplateForm(request.POST or None,instance=obj,organization=request.organization,initial=initial)
    if form.is_valid():
        saved=form.save(False); saved.organization=request.organization
        if saved.is_default: DocumentTemplate.objects.filter(organization=request.organization,kind=saved.kind,is_default=True).exclude(pk=saved.pk).update(is_default=False)
        saved.save(); audit(request,'document_template.saved',saved); return redirect('template_list')
    return render(request,'core/document_template_editor.html',{'form':form,'heading':'Documentsjabloon','cancel_url':reverse('template_list'),'layout':(obj.layout if obj and obj.layout else ['header','recipient','lines','totals','terms','footer'])})

@login_required
@owner_required
def integration_list(request): return render(request,'core/integrations.html',{'integrations':request.organization.integrations.all(),'calendars':request.organization.calendar_connections.select_related('membership__user')})
@login_required
@owner_required
def integration_form(request,integration_id=None): return _crud(request,IntegrationEndpoint,IntegrationEndpointForm,'Integratie','integration_list',integration_id)
@login_required
@owner_required
def calendar_connection_form(request,connection_id=None): return _crud(request,CalendarConnection,CalendarConnectionForm,'Agendakoppeling','integration_list',connection_id)

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.BILLING)
@require_POST
def payment_link_create(request,invoice_id):
    invoice=get_object_or_404(Invoice,pk=invoice_id,organization=request.organization); integration=request.organization.integrations.filter(kind='mollie',enabled=True).first()
    if not integration: messages.error(request,'Activeer eerst een Mollie-koppeling.'); return redirect('invoice_detail',invoice_id=invoice.id)
    link=PaymentLink.objects.create(organization=request.organization,invoice=invoice,amount=invoice.outstanding,created_by=request.user)
    try:
        data=json.dumps({'amount':{'currency':'EUR','value':f'{invoice.outstanding:.2f}'},'description':f'Factuur {invoice.number}','redirectUrl':request.build_absolute_uri(f'/facturen/{invoice.id}/'),'webhookUrl':request.build_absolute_uri('/api/mollie/webhook/')}).encode(); req=urllib.request.Request('https://api.mollie.com/v2/payments',data=data,headers={'Authorization':f'Bearer {integration.get_secret()}','Content-Type':'application/json'}); response=json.loads(urllib.request.urlopen(req,timeout=15).read()); link.provider_id=response['id']; link.checkout_url=response['_links']['checkout']['href']; link.status=PaymentLink.Status.OPEN; link.save(); audit(request,'payment_link.created',link)
    except Exception as exc: link.status=PaymentLink.Status.FAILED; link.save(update_fields=['status']); messages.error(request,f'Betaallink kon niet worden aangemaakt: {str(exc)[:180]}')
    return redirect('invoice_detail',invoice_id=invoice.id)

def _api_auth(request):
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    for endpoint in IntegrationEndpoint.objects.filter(kind='import',enabled=True).select_related('organization'):
        try:
            if token and hmac.compare_digest(endpoint.get_secret(),token): return endpoint
        except Exception: continue
    return None

@csrf_exempt
def api_customers(request):
    endpoint=_api_auth(request)
    if not endpoint: return JsonResponse({'error':'unauthorized'},status=401)
    if request.method=='GET': return JsonResponse({'results':[{'id':str(x.id),'name':x.legal_name,'email':x.email,'status':x.status} for x in endpoint.organization.customers.all()[:500]]})
    if request.method=='POST':
        try: data=json.loads(request.body); customer=endpoint.organization.customers.create(legal_name=data['name'],email=data.get('email',''),status=data.get('status','active')); return JsonResponse({'id':str(customer.id)},status=201)
        except (ValueError,KeyError): return JsonResponse({'error':'invalid_payload'},status=400)
    return JsonResponse({'error':'method_not_allowed'},status=405)

@csrf_exempt
def api_communications(request):
    endpoint=_api_auth(request)
    if not endpoint: return JsonResponse({'error':'unauthorized'},status=401)
    if request.method!='POST': return JsonResponse({'error':'method_not_allowed'},status=405)
    try:
        data=json.loads(request.body); customer=get_object_or_404(Customer,pk=data['customer_id'],organization=endpoint.organization); item=Communication.objects.create(organization=endpoint.organization,customer=customer,direction='in',status='received',subject=data['subject'][:250],body=data.get('body',''),sender=data.get('sender',''),recipient=data.get('recipient',''),external_id=data.get('external_id','')[:180],created_by=endpoint.organization.memberships.filter(role='owner',is_active=True).select_related('user').first().user); return JsonResponse({'id':str(item.id)},status=201)
    except (ValueError,KeyError,AttributeError): return JsonResponse({'error':'invalid_payload'},status=400)

@csrf_exempt
@require_POST
def mollie_webhook(request):
    payment_id=request.POST.get('id','')
    link=PaymentLink.objects.filter(provider_id=payment_id).select_related('organization','invoice').first()
    if not link: return JsonResponse({'ok':True})
    integration=link.organization.integrations.filter(kind='mollie',enabled=True).first()
    if integration:
        try:
            req=urllib.request.Request(f'https://api.mollie.com/v2/payments/{urllib.parse.quote(payment_id)}',headers={'Authorization':f'Bearer {integration.get_secret()}'}); data=json.loads(urllib.request.urlopen(req,timeout=15).read())
            if data.get('status')=='paid' and link.status!=PaymentLink.Status.PAID:
                with transaction.atomic(): link.status=PaymentLink.Status.PAID; link.paid_at=timezone.now(); link.save(update_fields=['status','paid_at']); Payment.objects.create(organization=link.organization,invoice=link.invoice,amount=link.amount,paid_on=timezone.localdate(),reference=f'Mollie {payment_id}',recorded_by=link.created_by)
        except Exception: pass
    return JsonResponse({'ok':True})

@login_required
@owner_required
def system_monitor(request):
    org=request.organization; alerts=list(org.system_alerts.filter(is_resolved=False)); low=[p for p in org.products.filter(track_stock=True) if p.stock_quantity<=p.minimum_stock]
    return render(request,'core/system_monitor.html',{'alerts':alerts,'low_stock':low,'failed_mail':org.communications.filter(status='failed').count(),'failed_hooks':org.webhook_deliveries.filter(status='failed').count()})

@login_required
@owner_required
@require_POST
def alert_resolve(request,alert_id):
    alert=get_object_or_404(SystemAlert,pk=alert_id,organization=request.organization); alert.is_resolved=True; alert.resolved_at=timezone.now(); alert.save(update_fields=['is_resolved','resolved_at']); audit(request,'alert.resolved',alert); return redirect('system_monitor')

@login_required
@roles_required(*MANAGER_ROLES)
def signature_list(request):
    token=request.session.pop('signature_token',None); return render(request,'core/signatures.html',{'requests':request.organization.signature_requests.select_related('contract','quote'),'token':token})

@login_required
@roles_required(*MANAGER_ROLES)
@require_POST
def signature_create(request):
    contract=get_object_or_404(Contract,pk=request.POST.get('contract'),organization=request.organization); email=request.POST.get('email','').strip(); raw=secrets.token_urlsafe(32); content=f'{contract.title}\n{contract.terms}\n{contract.start_date}\n{contract.end_date}'.encode()
    SignatureRequest.objects.create(organization=request.organization,contract=contract,signer_email=email,token_digest=hashlib.sha256(raw.encode()).hexdigest(),document_sha256=hashlib.sha256(content).hexdigest(),expires_at=timezone.now()+timedelta(days=14)); request.session['signature_token']=request.build_absolute_uri(f'/ondertekenen/{raw}/'); audit(request,'signature.created',contract,{'email':email}); return redirect('signature_list')

def signature_public(request,token):
    item=SignatureRequest.objects.filter(token_digest=hashlib.sha256(token.encode()).hexdigest(),status=SignatureRequest.Status.PENDING,expires_at__gt=timezone.now()).select_related('contract','organization').first()
    if not item: return render(request,'core/signature_public.html',{'invalid':True},status=410)
    if request.method=='POST':
        name=request.POST.get('name','').strip(); decision=request.POST.get('decision')
        if len(name)<2 or decision not in ('signed','declined'): messages.error(request,'Vul je naam in en kies een geldige actie.')
        else:
            item.signer_name=name; item.status=decision; item.signed_at=timezone.now(); item.ip_address=request.META.get('HTTP_X_FORWARDED_FOR',request.META.get('REMOTE_ADDR','')).split(',')[0].strip() or None; item.evidence={'user_agent':request.META.get('HTTP_USER_AGENT','')[:300],'accepted_text':decision=='signed'}; item.save(update_fields=['signer_name','status','signed_at','ip_address','evidence']); return render(request,'core/signature_public.html',{'completed':True,'item':item})
    return render(request,'core/signature_public.html',{'item':item})

@login_required
@roles_required(Membership.Role.OWNER,Membership.Role.CUSTOMER_MANAGER,Membership.Role.BILLING)
def data_import(request):
    form=DataImportForm(request.POST or None,request.FILES or None); result=None
    if form.is_valid():
        rows=list(csv.DictReader(io.StringIO(form.cleaned_data['file'].read().decode('utf-8-sig')),delimiter=';')); entity=form.cleaned_data['entity']; errors=[]; prepared=[]
        for number,row in enumerate(rows,start=2):
            try:
                if entity=='customers': prepared.append({'legal_name':row['naam'].strip(),'email':row.get('email','').strip()})
                elif entity=='products': prepared.append({'code':row['code'].strip(),'name':row['naam'].strip(),'unit_price':Decimal(row.get('prijs','0').replace(',','.'))})
                else: prepared.append({'customer':request.organization.customers.get(legal_name=row['klant'].strip()),'title':row['titel'].strip(),'start_date':date.fromisoformat(row['startdatum']),'value':Decimal(row.get('waarde','0').replace(',','.'))})
            except Exception as exc: errors.append(f'Regel {number}: {str(exc)[:120]}')
        created=0
        if not errors and not form.cleaned_data['dry_run']:
            with transaction.atomic():
                for data in prepared:
                    if entity=='customers': Customer.objects.create(organization=request.organization,**data)
                    elif entity=='products': Product.objects.create(organization=request.organization,**data)
                    else: Contract.objects.create(organization=request.organization,**data)
                    created+=1
            audit(request,'data.import',metadata={'entity':entity,'count':created})
        result={'valid':len(prepared),'created':created,'errors':errors,'dry_run':form.cleaned_data['dry_run']}
    return render(request,'core/data_import.html',{'form':form,'result':result})

@login_required
@owner_required
@require_POST
def webhook_test(request,integration_id):
    endpoint=get_object_or_404(IntegrationEndpoint,pk=integration_id,organization=request.organization,kind='webhook',enabled=True); delivery=WebhookDelivery.objects.create(organization=request.organization,endpoint=endpoint,event='integration.test',payload={'organization':request.organization.name,'time':timezone.now().isoformat()})
    try:
        body=json.dumps(delivery.payload).encode(); signature=hmac.new(endpoint.get_secret().encode(),body,hashlib.sha256).hexdigest(); req=urllib.request.Request(endpoint.endpoint,data=body,headers={'Content-Type':'application/json','X-ToolMigo-Signature':signature}); response=urllib.request.urlopen(req,timeout=10); delivery.status='sent'; delivery.response_code=response.status; delivery.sent_at=timezone.now(); endpoint.last_success_at=timezone.now(); endpoint.last_error=''; endpoint.save(update_fields=['last_success_at','last_error'])
    except Exception as exc: delivery.status='failed'; delivery.error=str(exc)[:1000]; endpoint.last_error=delivery.error; endpoint.save(update_fields=['last_error'])
    delivery.attempts=1; delivery.save(); audit(request,'webhook.test',delivery); return redirect('integration_list')

@login_required
def calendar_ics(request):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//ToolMigo//CRM//NL']
    for event in request.organization.appointments.filter(is_cancelled=False):
        lines.extend(['BEGIN:VEVENT',f'UID:{event.id}@toolmigo',f'DTSTART:{event.start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',f'DTEND:{event.end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',f'SUMMARY:{event.title.replace(chr(10)," ")}',f'LOCATION:{event.location.replace(chr(10)," ")}','END:VEVENT'])
    lines.append('END:VCALENDAR'); response=JsonResponse({},status=200); response.content='\r\n'.join(lines); response['Content-Type']='text/calendar; charset=utf-8'; response['Content-Disposition']='attachment; filename="toolmigo-agenda.ics"'; return response

@login_required
@owner_required
@require_POST
def calendar_sync(request,connection_id):
    connection=get_object_or_404(CalendarConnection,pk=connection_id,organization=request.organization,enabled=True)
    if connection.provider!='caldav' or not connection.endpoint:
        connection.last_error='Voor Google en Microsoft is OAuth-configuratie vereist; gebruik voorlopig iCalendar-export.'; connection.save(update_fields=['last_error']); messages.error(request,connection.last_error); return redirect('integration_list')
    try:
        from .encryption import decrypt_secret
        auth=base64.b64encode(f'{connection.account}:{decrypt_secret(connection.secret_encrypted)}'.encode()).decode()
        events=request.organization.appointments.filter(is_cancelled=False,participants=connection.membership).distinct()
        for event in events:
            ics='\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0','BEGIN:VEVENT',f'UID:{event.id}@toolmigo',f'DTSTART:{event.start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',f'DTEND:{event.end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',f'SUMMARY:{event.title}','END:VEVENT','END:VCALENDAR']); url=connection.endpoint.rstrip('/')+f'/{event.id}.ics'; req=urllib.request.Request(url,data=ics.encode(),method='PUT',headers={'Authorization':f'Basic {auth}','Content-Type':'text/calendar; charset=utf-8'}); urllib.request.urlopen(req,timeout=12).read()
        connection.last_sync_at=timezone.now(); connection.last_error=''; connection.save(update_fields=['last_sync_at','last_error']); audit(request,'calendar.synced',connection,{'events':events.count()}); messages.success(request,f'{events.count()} afspraak/afspraken gesynchroniseerd.')
    except Exception as exc: connection.last_error=str(exc)[:1000]; connection.save(update_fields=['last_error']); messages.error(request,'Agenda synchroniseren mislukt; controleer endpoint en account.')
    return redirect('integration_list')

def service_worker(request):
    response=FileResponse(open(settings.BASE_DIR/'static/js/service-worker.js','rb'),content_type='application/javascript'); response['Service-Worker-Allowed']='/'; return response
