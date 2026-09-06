from django.test import Client, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import get_connection
from unittest.mock import patch
from django.urls import reverse
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import Appointment, AppointmentType, AuditEvent, Board, BoardColumn, Contact, Customer, CustomerActivity, EmailDelivery, Invoice, InvoiceLine, Membership, Organization, OrganizationEmailSettings, Payment, Product, Quote, QuoteLine, Task, TaskAttachment, TaskChecklistItem, User

class TenantSecurityTests(TestCase):
    def setUp(self):
        self.a=Organization.objects.create(name='Bedrijf A',slug='a'); self.b=Organization.objects.create(name='Bedrijf B',slug='b')
        self.owner=User.objects.create_user(email='owner@example.nl',display_name='Owner',password='CorrectHorseBattery!1')
        self.worker=User.objects.create_user(email='worker@example.nl',display_name='Worker',password='CorrectHorseBattery!1')
        self.foreign=User.objects.create_user(email='foreign@example.nl',display_name='Foreign',password='CorrectHorseBattery!1')
        self.owner_member=Membership.objects.create(organization=self.a,user=self.owner,role=Membership.Role.OWNER)
        Membership.objects.create(organization=self.a,user=self.worker,role=Membership.Role.EMPLOYEE)
        self.foreign_member=Membership.objects.create(organization=self.b,user=self.foreign,role=Membership.Role.OWNER)
    def test_login_required(self): self.assertRedirects(self.client.get('/'),'/login/?next=/')
    def test_employee_cannot_open_team_management(self):
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('team')),reverse('dashboard'))
    def test_owner_cannot_toggle_foreign_membership(self):
        self.client.force_login(self.owner); response=self.client.post(reverse('team_toggle',args=[self.foreign_member.id])); self.assertEqual(response.status_code,404)
    def test_owner_cannot_disable_self(self):
        self.client.force_login(self.owner); self.client.post(reverse('team_toggle',args=[self.owner_member.id])); self.owner_member.refresh_from_db(); self.assertTrue(self.owner_member.is_active)
    def test_team_create_is_scoped_and_audited(self):
        self.client.force_login(self.owner); response=self.client.post(reverse('team_add'),{'display_name':'Nieuw','email':'nieuw@example.nl','role':'approver','password1':'LongUniquePassword!728','password2':'LongUniquePassword!728'})
        self.assertRedirects(response,reverse('team')); self.assertTrue(Membership.objects.filter(organization=self.a,user__email='nieuw@example.nl').exists()); self.assertFalse(Membership.objects.filter(organization=self.b,user__email='nieuw@example.nl').exists()); self.assertTrue(AuditEvent.objects.filter(organization=self.a,action='team.member_created').exists())
    def test_successful_login_is_audited(self):
        response=self.client.post(reverse('login'),{'username':'owner@example.nl','password':'CorrectHorseBattery!1'}); self.assertRedirects(response,reverse('dashboard')); self.assertTrue(AuditEvent.objects.filter(actor=self.owner,action='auth.login').exists())
    def test_only_owner_can_open_email_settings(self):
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('email_settings')),reverse('dashboard')); self.client.force_login(self.owner); self.assertEqual(self.client.get(reverse('email_settings')).status_code,200)
    def test_owner_saves_encrypted_smtp_password(self):
        self.client.force_login(self.owner); response=self.client.post(reverse('email_settings'),{'host':'smtp.example.nl','port':'587','username':'mailer','password':'SuperSecretSMTP!','from_email':'facturen@example.nl','use_tls':'on','is_active':'on'}); self.assertRedirects(response,reverse('email_settings')); config=OrganizationEmailSettings.objects.get(organization=self.a); self.assertNotIn('SuperSecretSMTP!',config.password_encrypted); self.assertEqual(config.get_password(),'SuperSecretSMTP!')
    def test_all_account_roles_are_available(self):
        self.assertEqual(dict(Membership.Role.choices),{
            'owner':'Bedrijfsbeheerder','approver':'Facturatie','employee':'Medewerker',
            'sales':'Verkoop','customer_manager':'Klantbeheer','planner':'Planning',
            'project_manager':'Projectbeheer','support':'Support',
        })
    def test_owner_can_edit_account_and_promote_role(self):
        self.client.force_login(self.owner)
        membership=self.worker.memberships.get(organization=self.a)
        response=self.client.post(reverse('team_edit',args=[membership.id]),{'display_name':'Nieuwe naam','email':'nieuw-werk@example.nl','role':'project_manager'})
        self.assertRedirects(response,reverse('team')); membership.refresh_from_db(); self.worker.refresh_from_db()
        self.assertEqual(membership.role,Membership.Role.PROJECT_MANAGER); self.assertEqual(self.worker.display_name,'Nieuwe naam'); self.assertEqual(self.worker.email,'nieuw-werk@example.nl')
        self.assertTrue(AuditEvent.objects.filter(action='team.member_updated',target_id=str(membership.id)).exists())
    def test_removed_account_loses_access_but_history_is_kept(self):
        self.client.force_login(self.owner); membership=self.worker.memberships.get(organization=self.a)
        response=self.client.post(reverse('team_remove',args=[membership.id])); self.assertRedirects(response,reverse('team'))
        membership.refresh_from_db(); self.worker.refresh_from_db()
        self.assertTrue(membership.is_removed); self.assertFalse(membership.is_active); self.assertFalse(self.worker.is_active); self.assertIsNotNone(membership.removed_at)
        self.assertFalse(self.a.memberships.filter(is_removed=False,user=self.worker).exists()); self.assertTrue(AuditEvent.objects.filter(action='team.member_removed',target_id=str(membership.id)).exists())
        self.client.logout(); response=self.client.post(reverse('login'),{'username':'worker@example.nl','password':'CorrectHorseBattery!1'}); self.assertEqual(response.status_code,200); self.assertNotIn('_auth_user_id',self.client.session)
    def test_owner_cannot_remove_own_account(self):
        self.client.force_login(self.owner); self.client.post(reverse('team_remove',args=[self.owner_member.id])); self.owner_member.refresh_from_db(); self.owner.refresh_from_db()
        self.assertFalse(self.owner_member.is_removed); self.assertTrue(self.owner.is_active)
    def test_auditlog_is_only_visible_to_owner(self):
        AuditEvent.objects.create(organization=self.a,actor=self.owner,action='geheime.auditactie')
        self.client.force_login(self.owner); owner_response=self.client.get(reverse('dashboard'))
        self.assertContains(owner_response,'AUDITLOG'); self.assertContains(owner_response,'geheime.auditactie'); self.assertNotContains(owner_response,'VOORTGANG')
        self.client.force_login(self.worker); worker_response=self.client.get(reverse('dashboard'))
        self.assertNotContains(worker_response,'AUDITLOG'); self.assertNotContains(worker_response,'geheime.auditactie'); self.assertNotContains(worker_response,'VOORTGANG')

class CustomerSecurityTests(TestCase):
    def setUp(self):
        self.a=Organization.objects.create(name='Bedrijf A',slug='customer-a'); self.b=Organization.objects.create(name='Bedrijf B',slug='customer-b')
        self.user=User.objects.create_user(email='klantbeheer@example.nl',display_name='Klantbeheer',password='CorrectHorseBattery!1')
        Membership.objects.create(organization=self.a,user=self.user,role=Membership.Role.OWNER)
        self.own=Customer.objects.create(organization=self.a,legal_name='Eigen Klant B.V.',kvk_number='12345678')
        self.foreign=Customer.objects.create(organization=self.b,legal_name='Vreemde Klant B.V.',kvk_number='87654321')
        self.client.force_login(self.user)
    def test_foreign_customer_is_never_visible(self):
        response=self.client.get(reverse('customer_list')); self.assertContains(response,'Eigen Klant B.V.'); self.assertNotContains(response,'Vreemde Klant B.V.'); self.assertContains(response,'<span class="customer-avatar">E</span>',html=True)
    def test_foreign_customer_detail_and_edit_return_404(self):
        self.assertEqual(self.client.get(reverse('customer_detail',args=[self.foreign.id])).status_code,404)
        self.assertEqual(self.client.get(reverse('customer_edit',args=[self.foreign.id])).status_code,404)
    def test_customer_creation_is_scoped_and_audited(self):
        response=self.client.post(reverse('customer_create'),{'kind':'company','legal_name':'Nieuwe Klant','status':'active','payment_term_days':'14','labels_text':'belangrijk, onderhoud'})
        customer=Customer.objects.get(legal_name='Nieuwe Klant'); self.assertEqual(customer.organization,self.a); self.assertEqual(customer.labels,['belangrijk','onderhoud']); self.assertRedirects(response,reverse('customer_detail',args=[customer.id])); self.assertTrue(AuditEvent.objects.filter(organization=self.a,action='customer.created').exists())
    def test_contact_organization_is_inherited_from_customer(self):
        contact=Contact(customer=self.own,organization=self.b,first_name='Jan'); contact.save(); self.assertEqual(contact.organization,self.a)
    def test_note_is_scoped_to_customer_organization(self):
        self.client.post(reverse('customer_note',args=[self.own.id]),{'kind':'call','body':'Klant gesproken.'}); activity=CustomerActivity.objects.get(customer=self.own,kind='call'); self.assertEqual(activity.organization,self.a)
    def test_duplicate_kvk_is_rejected_within_organization(self):
        response=self.client.post(reverse('customer_create'),{'kind':'company','legal_name':'Dubbel','status':'active','payment_term_days':'14','kvk_number':'12345678'}); self.assertEqual(response.status_code,200); self.assertContains(response,'bestaat al')

class QuoteWorkflowTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='ToolMigo Test',slug='quotes'); self.other=Organization.objects.create(name='Andere Org',slug='quotes-other')
        self.maker=User.objects.create_user(email='maker@example.nl',display_name='Maker',password='CorrectHorseBattery!1'); self.approver=User.objects.create_user(email='approver@example.nl',display_name='Approver',password='CorrectHorseBattery!1')
        Membership.objects.create(organization=self.org,user=self.maker,role=Membership.Role.EMPLOYEE); Membership.objects.create(organization=self.org,user=self.approver,role=Membership.Role.BILLING)
        self.customer=Customer.objects.create(organization=self.org,legal_name='Klant B.V.'); self.product=Product.objects.create(organization=self.org,code='ADV',name='Advies',unit='uur',unit_price='100.00',vat_rate='21')
        self.quote=Quote.objects.create(organization=self.org,customer=self.customer,created_by=self.maker,title='Adviesofferte',issue_date=date.today(),valid_until=date.today()+timedelta(days=30))
        self.line=QuoteLine.objects.create(organization=self.org,quote=self.quote,product=self.product,description='Advies',quantity='2.00',unit='uur',unit_price='100.00',discount_percent='10',vat_rate='21')
    def test_money_totals_are_decimal_and_rounded(self):
        self.assertEqual(self.line.net_amount,Decimal('180.00')); self.assertEqual(self.line.vat_amount,Decimal('37.80')); self.assertEqual(self.quote.total,Decimal('217.80'))
    def test_submit_requires_line_and_locks_editing(self):
        self.client.force_login(self.maker); self.client.post(reverse('quote_submit',args=[self.quote.id])); self.quote.refresh_from_db(); self.assertEqual(self.quote.status,Quote.Status.SUBMITTED)
        response=self.client.post(reverse('quote_line_delete',args=[self.quote.id,self.line.id])); self.assertEqual(response.status_code,409); self.assertTrue(QuoteLine.objects.filter(pk=self.line.id).exists())
    def test_maker_cannot_approve_own_quote(self):
        self.quote.status=Quote.Status.SUBMITTED; self.quote.save(); self.client.force_login(self.maker); self.client.post(reverse('quote_approve',args=[self.quote.id])); self.quote.refresh_from_db(); self.assertEqual(self.quote.status,Quote.Status.SUBMITTED); self.assertEqual(self.quote.number,'')
    def test_approver_assigns_expected_number(self):
        self.quote.status=Quote.Status.SUBMITTED; self.quote.save(); self.client.force_login(self.approver); self.client.post(reverse('quote_approve',args=[self.quote.id])); self.quote.refresh_from_db(); self.assertEqual(self.quote.status,Quote.Status.APPROVED); self.assertRegex(self.quote.number,r'^TM-\d{4}-0001$'); self.assertTrue(AuditEvent.objects.filter(action='quote.approved',target_id=str(self.quote.id)).exists())
    def test_foreign_quote_is_hidden(self):
        foreign_customer=Customer.objects.create(organization=self.other,legal_name='Verborgen'); foreign=Quote.objects.create(organization=self.other,customer=foreign_customer,created_by=self.maker,issue_date=date.today(),valid_until=date.today())
        self.client.force_login(self.maker); self.assertEqual(self.client.get(reverse('quote_detail',args=[foreign.id])).status_code,404)
    def test_pdf_is_generated(self):
        self.client.force_login(self.maker); response=self.client.get(reverse('quote_pdf',args=[self.quote.id])); self.assertEqual(response.status_code,200); self.assertEqual(response['Content-Type'],'application/pdf'); self.assertTrue(response.content.startswith(b'%PDF'))
    def test_product_can_be_changed_and_deleted_without_losing_line_text(self):
        self.client.force_login(self.maker); self.client.post(reverse('product_delete',args=[self.product.id])); self.assertFalse(Product.objects.filter(pk=self.product.id).exists()); self.line.refresh_from_db(); self.assertIsNone(self.line.product); self.assertEqual(self.line.description,'Advies')
    def test_draft_quote_can_be_deleted(self):
        quote_id=self.quote.id; self.client.force_login(self.maker); self.assertRedirects(self.client.post(reverse('quote_delete',args=[quote_id])),reverse('quote_list')); self.quote.refresh_from_db(); self.assertTrue(self.quote.is_archived); self.assertNotContains(self.client.get(reverse('quote_list')),'Adviesofferte'); self.assertEqual(self.client.get(reverse('quote_detail',args=[quote_id])).status_code,404); self.assertTrue(AuditEvent.objects.filter(action='quote.archived',target_id=str(quote_id)).exists())
    def test_sent_quote_can_be_removed_from_overview(self):
        self.quote.status=Quote.Status.SENT; self.quote.number='TM-2026-0099'; self.quote.save(); self.client.force_login(self.maker); self.client.post(reverse('quote_delete',args=[self.quote.id])); self.quote.refresh_from_db(); self.assertTrue(self.quote.is_archived); self.assertIsNotNone(self.quote.archived_at)

class InvoiceWorkflowTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Factuurbedrijf',slug='invoices',iban='NL00BANK0000000000',kvk_number='12345678',vat_id='NL000000000B01')
        self.maker=User.objects.create_user(email='imaker@example.nl',display_name='Maker',password='CorrectHorseBattery!1'); self.approver=User.objects.create_user(email='iapprove@example.nl',display_name='Goedkeurder',password='CorrectHorseBattery!1')
        Membership.objects.create(organization=self.org,user=self.maker,role=Membership.Role.EMPLOYEE); Membership.objects.create(organization=self.org,user=self.approver,role=Membership.Role.BILLING)
        self.customer=Customer.objects.create(organization=self.org,legal_name='Klant Factuur B.V.',email='finance@example.nl',address='Straat 1',postal_code='1000AA',city='Amsterdam',payment_term_days=14)
        self.invoice=Invoice.objects.create(organization=self.org,customer=self.customer,created_by=self.maker,issue_date=date.today(),delivery_date=date.today(),due_date=date.today()+timedelta(days=14))
        InvoiceLine.objects.create(organization=self.org,invoice=self.invoice,description='Dienst',quantity='2',unit='uur',unit_price='50',vat_rate='21')
    def approve(self):
        self.invoice.status=Invoice.Status.SUBMITTED; self.invoice.save(); self.client.force_login(self.approver); self.client.post(reverse('invoice_approve',args=[self.invoice.id])); self.invoice.refresh_from_db()
    def test_approval_assigns_invoice_sequence_and_snapshot(self):
        self.approve(); self.assertEqual(self.invoice.number,f'TM-{date.today().year}-0001'); self.assertEqual(self.invoice.customer_name_snapshot,'Klant Factuur B.V.'); self.assertEqual(self.invoice.status,Invoice.Status.APPROVED)
    def test_maker_cannot_approve_own_invoice(self):
        self.invoice.status=Invoice.Status.SUBMITTED; self.invoice.save(); self.client.force_login(self.maker); self.client.post(reverse('invoice_approve',args=[self.invoice.id])); self.invoice.refresh_from_db(); self.assertEqual(self.invoice.status,Invoice.Status.SUBMITTED); self.assertEqual(self.invoice.number,'')
    def test_invoice_pdf(self):
        self.client.force_login(self.maker); response=self.client.get(reverse('invoice_pdf',args=[self.invoice.id])); self.assertTrue(response.content.startswith(b'%PDF')); self.assertEqual(response['Content-Type'],'application/pdf')
    def test_payment_updates_status(self):
        self.invoice.status=Invoice.Status.SENT; self.invoice.save(); self.client.force_login(self.maker); self.client.post(reverse('payment_add',args=[self.invoice.id]),{'amount':'60.50','paid_on':date.today(),'reference':'Bank'}); self.invoice.refresh_from_db(); self.assertEqual(self.invoice.status,Invoice.Status.PARTIAL); self.assertEqual(self.invoice.paid_amount,Decimal('60.50'))
    def test_full_credit_copies_negative_lines(self):
        self.invoice.status=Invoice.Status.SENT; self.invoice.number='TM-2026-0001'; self.invoice.save(); self.client.force_login(self.maker); response=self.client.post(reverse('credit_create',args=[self.invoice.id])); credit=Invoice.objects.get(original_invoice=self.invoice); self.assertRedirects(response,reverse('invoice_detail',args=[credit.id])); self.assertEqual(credit.total,Decimal('-121.00'))
    def test_batch_dispatch_sends_each_approved_document(self):
        self.approve(); config=OrganizationEmailSettings.objects.create(organization=self.org,host='smtp.example.nl',from_email='facturen@example.nl'); config.set_password('test-secret'); config.save(); self.client.force_login(self.approver)
        with patch('core.views.get_connection',return_value=get_connection('django.core.mail.backends.locmem.EmailBackend')): self.client.post(reverse('dispatch_approved'))
        self.invoice.refresh_from_db(); self.assertEqual(self.invoice.status,Invoice.Status.SENT); self.assertTrue(EmailDelivery.objects.filter(document_id=self.invoice.id,status=EmailDelivery.Status.SENT).exists())
    def test_employee_cannot_dispatch_approved_documents(self):
        self.approve(); self.client.force_login(self.maker); response=self.client.post(reverse('dispatch_approved')); self.assertRedirects(response,reverse('dashboard')); self.invoice.refresh_from_db(); self.assertEqual(self.invoice.status,Invoice.Status.APPROVED); self.assertFalse(EmailDelivery.objects.exists())
    def test_approver_can_remove_delivery_from_history(self):
        delivery=EmailDelivery.objects.create(organization=self.org,document_type='invoice',document_id=self.invoice.id,recipient='finance@example.nl',subject='Test',status=EmailDelivery.Status.SENT,requested_by=self.approver); self.client.force_login(self.approver); self.assertRedirects(self.client.post(reverse('delivery_delete',args=[delivery.id])),reverse('outbox')); delivery.refresh_from_db(); self.assertTrue(delivery.is_archived); self.assertNotContains(self.client.get(reverse('outbox')),'finance@example.nl'); self.assertTrue(AuditEvent.objects.filter(action='email_delivery.archived',target_id=str(delivery.id)).exists())
    def test_employee_cannot_remove_delivery(self):
        delivery=EmailDelivery.objects.create(organization=self.org,document_type='invoice',document_id=self.invoice.id,recipient='finance@example.nl',subject='Test',status=EmailDelivery.Status.SENT,requested_by=self.approver); self.client.force_login(self.maker); self.assertRedirects(self.client.post(reverse('delivery_delete',args=[delivery.id])),reverse('dashboard')); delivery.refresh_from_db(); self.assertFalse(delivery.is_archived)
    def test_draft_invoice_can_be_deleted(self):
        invoice_id=self.invoice.id; self.client.force_login(self.maker); self.assertRedirects(self.client.post(reverse('invoice_delete',args=[invoice_id])),reverse('invoice_list')); self.invoice.refresh_from_db(); self.assertTrue(self.invoice.is_archived); self.assertEqual(self.client.get(reverse('invoice_detail',args=[invoice_id])).status_code,404); self.assertTrue(AuditEvent.objects.filter(action='invoice.archived',target_id=str(invoice_id)).exists())
    def test_sent_invoice_can_be_removed_from_overview(self):
        self.invoice.status=Invoice.Status.SENT; self.invoice.number='TM-2026-0099'; self.invoice.save(); self.client.force_login(self.maker); self.client.post(reverse('invoice_delete',args=[self.invoice.id])); self.invoice.refresh_from_db(); self.assertTrue(self.invoice.is_archived); self.assertIsNotNone(self.invoice.archived_at); self.assertNotContains(self.client.get(reverse('invoice_list')),'TM-2026-0099')

class CalendarTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Agenda Org',slug='agenda-org'); self.other=Organization.objects.create(name='Andere Agenda',slug='agenda-other'); self.user=User.objects.create_user(email='agenda@example.nl',display_name='Planner',password='CorrectHorseBattery!1'); self.member=Membership.objects.create(organization=self.org,user=self.user,role=Membership.Role.EMPLOYEE); self.kind=AppointmentType.objects.create(organization=self.org,name='Werk',color='#239F7F'); self.client.force_login(self.user)
        base=timezone.now().replace(hour=10,minute=0,second=0,microsecond=0)+timedelta(days=1); self.base=base
    def payload(self,**extra):
        data={'title':'Klantbezoek','appointment_type':str(self.kind.id),'participants':[str(self.member.id)],'start':timezone.localtime(self.base).strftime('%Y-%m-%dT%H:%M'),'end':timezone.localtime(self.base+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'reminder_minutes':'30','recurrence':'none'}; data.update(extra); return data
    def test_appointment_is_scoped_and_visible(self):
        response=self.client.post(reverse('appointment_create'),self.payload()); item=Appointment.objects.get(title='Klantbezoek'); self.assertEqual(item.organization,self.org); self.assertRedirects(response,f"{reverse('calendar')}?datum={timezone.localtime(item.start).date()}"); self.assertContains(self.client.get(reverse('calendar')+'?weergave=week&datum='+timezone.localtime(item.start).date().isoformat()),'Klantbezoek')
    def test_foreign_appointment_is_hidden(self):
        foreign=Appointment.objects.create(organization=self.other,title='Verborgen',start=self.base,end=self.base+timedelta(hours=1),created_by=self.user); self.assertEqual(self.client.get(reverse('appointment_detail',args=[foreign.id])).status_code,404)
    def test_weekly_recurrence_creates_real_occurrences(self):
        until=timezone.localtime(self.base).date()+timedelta(days=21); self.client.post(reverse('appointment_create'),self.payload(recurrence='weekly',recurrence_until=until.isoformat())); self.assertEqual(Appointment.objects.filter(organization=self.org,title='Klantbezoek').count(),4)
    def test_conflict_requires_explicit_confirmation(self):
        first=Appointment.objects.create(organization=self.org,title='Bestaand',start=self.base,end=self.base+timedelta(hours=1),created_by=self.user); first.participants.add(self.member)
        response=self.client.post(reverse('appointment_create'),self.payload()); self.assertEqual(response.status_code,200); self.assertContains(response,'Planningsconflict'); self.assertEqual(Appointment.objects.filter(organization=self.org).count(),1)
        self.client.post(reverse('appointment_create'),self.payload(confirm_conflict='1')); self.assertEqual(Appointment.objects.filter(organization=self.org).count(),2)
    def test_cancel_keeps_history(self):
        item=Appointment.objects.create(organization=self.org,title='Annuleren',start=self.base,end=self.base+timedelta(hours=1),created_by=self.user); self.client.post(reverse('appointment_cancel',args=[item.id])); item.refresh_from_db(); self.assertTrue(item.is_cancelled); self.assertTrue(AuditEvent.objects.filter(action='appointment.cancelled',target_id=str(item.id)).exists())

class KanbanTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Taken Org',slug='taken-org'); self.other=Organization.objects.create(name='Andere Taken',slug='taken-other'); self.user=User.objects.create_user(email='taken@example.nl',display_name='Planner',password='CorrectHorseBattery!1'); self.member=Membership.objects.create(organization=self.org,user=self.user,role=Membership.Role.OWNER); self.board=Board.objects.create(organization=self.org,name='Werk',is_default=True); self.todo=BoardColumn.objects.create(board=self.board,name='Te doen',position=1); self.done=BoardColumn.objects.create(board=self.board,name='Klaar',position=2,is_done=True); self.task=Task.objects.create(board=self.board,column=self.todo,title='Veilige taak',created_by=self.user); self.task.assignees.add(self.member); self.client.force_login(self.user)
    def test_board_and_task_are_visible(self):
        response=self.client.get(reverse('board_detail',args=[self.board.id])); self.assertContains(response,'Veilige taak'); self.assertContains(response,'Te doen')
    def test_foreign_board_is_hidden(self):
        foreign=Board.objects.create(organization=self.other,name='Verborgen'); self.assertEqual(self.client.get(reverse('board_detail',args=[foreign.id])).status_code,404)
    def test_move_to_done_sets_completion(self):
        response=self.client.post(reverse('task_move',args=[self.board.id,self.task.id]),data='{"column_id":"'+str(self.done.id)+'","position":1}',content_type='application/json'); self.assertEqual(response.status_code,200); self.task.refresh_from_db(); self.assertEqual(self.task.column,self.done); self.assertIsNotNone(self.task.completed_at)
    def test_move_cannot_use_foreign_column(self):
        foreign_board=Board.objects.create(organization=self.other,name='Anders'); foreign_column=BoardColumn.objects.create(board=foreign_board,name='Gestolen'); response=self.client.post(reverse('task_move',args=[self.board.id,self.task.id]),data='{"column_id":"'+str(foreign_column.id)+'"}',content_type='application/json'); self.assertEqual(response.status_code,404); self.task.refresh_from_db(); self.assertEqual(self.task.column,self.todo)
    def test_my_tasks_filter_hides_unassigned(self):
        Task.objects.create(board=self.board,column=self.todo,title='Niet van mij',created_by=self.user); response=self.client.get(reverse('board_detail',args=[self.board.id])+'?mine=1'); self.assertContains(response,'Veilige taak'); self.assertNotContains(response,'Niet van mij')
    def test_checklist_toggle_is_scoped(self):
        item=TaskChecklistItem.objects.create(task=self.task,text='Controleren'); self.client.post(reverse('checklist_toggle',args=[self.board.id,self.task.id,item.id])); item.refresh_from_db(); self.assertTrue(item.is_done)
    def test_foreign_attachment_download_is_hidden(self):
        foreign_board=Board.objects.create(organization=self.other,name='Bestanden'); foreign_column=BoardColumn.objects.create(board=foreign_board,name='Open'); foreign_task=Task.objects.create(board=foreign_board,column=foreign_column,title='Verborgen',created_by=self.user); attachment=TaskAttachment.objects.create(task=foreign_task,uploaded_by=self.user,file='missing.txt',original_name='missing.txt'); self.assertEqual(self.client.get(reverse('attachment_download',args=[foreign_board.id,foreign_task.id,attachment.id])).status_code,404)

class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Profiel Org',slug='profiel-org'); self.user=User.objects.create_user(email='profiel@example.nl',display_name='Oude naam',password='CorrectHorseBattery!1'); Membership.objects.create(organization=self.org,user=self.user,role=Membership.Role.EMPLOYEE); self.client.force_login(self.user)
    def test_user_can_update_own_settings(self):
        response=self.client.post(reverse('profile_settings'),{'display_name':'Nieuwe naam','email':'nieuw@example.nl','theme_preference':'dark'}); self.assertRedirects(response,reverse('profile_settings')); self.user.refresh_from_db(); self.assertEqual(self.user.display_name,'Nieuwe naam'); self.assertEqual(self.user.email,'nieuw@example.nl'); self.assertEqual(self.user.theme_preference,'dark'); self.assertTrue(AuditEvent.objects.filter(actor=self.user,action='profile.updated').exists())
    def test_valid_avatar_can_be_uploaded_and_viewed(self):
        gif=SimpleUploadedFile('avatar.gif',b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',content_type='image/gif'); self.client.post(reverse('profile_settings'),{'display_name':self.user.display_name,'email':self.user.email,'theme_preference':'system','avatar':gif}); self.user.refresh_from_db(); self.assertTrue(self.user.avatar); self.assertEqual(self.client.get(reverse('profile_avatar',args=[self.user.id])).status_code,200)
    def test_invalid_avatar_is_rejected(self):
        bad=SimpleUploadedFile('avatar.jpg',b'geen echte afbeelding',content_type='image/jpeg'); response=self.client.post(reverse('profile_settings'),{'display_name':self.user.display_name,'email':self.user.email,'theme_preference':'system','avatar':bad}); self.assertEqual(response.status_code,200); self.user.refresh_from_db(); self.assertFalse(self.user.avatar)
