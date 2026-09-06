from django.test import Client, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import get_connection
from unittest.mock import patch
import pyotp
import json
from django.urls import reverse
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import Appointment, AppointmentType, AuditEvent, BankTransaction, Board, BoardColumn, Communication, Contact, Contract, Customer, CustomerActivity, DocumentTemplate, EmailDelivery, IntegrationEndpoint, Invoice, InvoiceLine, Membership, Opportunity, Organization, OrganizationEmailSettings, Payment, PaymentLink, PaymentReminder, PortalAccess, PortalDecision, Product, Project, Quote, QuoteLine, RecurringInvoiceSchedule, ReminderPolicy, ServiceTicket, SignatureRequest, StockMovement, SystemAlert, Task, TaskAttachment, TaskChecklistItem, TimeEntry, User
from .automation import generate_recurring_drafts, queue_payment_reminders, refresh_system_alerts
from .extensions import _parse_bank_rows

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
    def test_dashboard_marks_only_dashboard_navigation_active(self):
        self.client.force_login(self.owner); response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.content.count(b'class="active"'),1)
    def test_favicon_uses_toolmigo_logo(self): self.assertRedirects(self.client.get('/favicon.ico'),'/static/img/toolmigo-logo.jpeg',status_code=301,fetch_redirect_response=False)
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
    def test_two_factor_cannot_be_bypassed_after_password(self):
        secret=pyotp.random_base32(); self.owner.set_totp_secret(secret); self.owner.totp_enabled=True; self.owner.save()
        response=self.client.post(reverse('login'),{'username':'owner@example.nl','password':'CorrectHorseBattery!1'})
        self.assertRedirects(response,reverse('two_factor_login')); self.assertNotIn('_auth_user_id',self.client.session)
        self.assertEqual(self.client.post(reverse('two_factor_login'),{'code':'000000'}).status_code,200); self.assertNotIn('_auth_user_id',self.client.session)
        self.assertRedirects(self.client.post(reverse('two_factor_login'),{'code':pyotp.TOTP(secret).now()}),reverse('dashboard')); self.assertIn('_auth_user_id',self.client.session)
    def test_owner_can_reset_team_member_two_factor(self):
        secret=pyotp.random_base32(); self.worker.set_totp_secret(secret); self.worker.totp_enabled=True; self.worker.recovery_code_hashes=['hash']; self.worker.save()
        self.client.force_login(self.owner); membership=self.worker.memberships.get(organization=self.a); self.assertRedirects(self.client.post(reverse('team_reset_two_factor',args=[membership.id])),reverse('team'))
        self.worker.refresh_from_db(); self.assertFalse(self.worker.totp_enabled); self.assertEqual(self.worker.recovery_code_hashes,[]); self.assertTrue(AuditEvent.objects.filter(action='auth.2fa_admin_reset').exists())
    def test_only_owner_can_open_email_settings(self):
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('email_settings')),reverse('dashboard')); self.client.force_login(self.owner); self.assertEqual(self.client.get(reverse('email_settings')).status_code,200)
    def test_only_owner_can_change_organization_settings(self):
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('organization_settings')),reverse('dashboard'))
        self.client.force_login(self.owner); response=self.client.post(reverse('organization_settings'),{'name':'Nieuwe Bedrijfsnaam','address':'Straat 1','postal_code':'1234 AB','city':'Utrecht','kvk_number':'12345678','vat_id':'NL001','iban':'NL91ABNA0417164300','payment_term_days':14,'primary_color':'#123abc','quote_prefix':'OFF','invoice_prefix':'FAC','quote_valid_days':30,'default_quote_terms':'Voorwaarden','default_invoice_notes':'Bedankt'})
        self.assertRedirects(response,reverse('organization_settings')); self.a.refresh_from_db(); self.assertEqual(self.a.name,'Nieuwe Bedrijfsnaam')
    def test_global_search_is_tenant_scoped(self):
        Customer.objects.create(organization=self.a,legal_name='Vindbare Eigen Klant'); Customer.objects.create(organization=self.b,legal_name='Vindbare Vreemde Klant')
        self.client.force_login(self.owner); response=self.client.get(reverse('global_search'),{'q':'Vindbare'}); self.assertContains(response,'Eigen Klant'); self.assertNotContains(response,'Vreemde Klant')
    def test_trash_is_owner_only_and_customer_can_be_restored(self):
        customer=Customer.objects.create(organization=self.a,legal_name='Herstelbare Klant',status=Customer.Status.ARCHIVED,archived_at=timezone.now(),archived_by=self.owner)
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('trash')),reverse('dashboard'))
        self.client.force_login(self.owner); self.assertContains(self.client.get(reverse('trash')),'Herstelbare Klant'); self.assertRedirects(self.client.post(reverse('trash_restore',args=['customer',customer.id])),reverse('trash')); customer.refresh_from_db(); self.assertEqual(customer.status,Customer.Status.ACTIVE); self.assertIsNone(customer.archived_at)
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

class SalesProjectSecurityTests(TestCase):
    def setUp(self):
        self.a=Organization.objects.create(name='Uitvoering A',slug='uitvoering-a'); self.b=Organization.objects.create(name='Uitvoering B',slug='uitvoering-b'); self.user=User.objects.create_user(email='project@example.nl',display_name='Projectbeheer',password='CorrectHorseBattery!1'); self.member=Membership.objects.create(organization=self.a,user=self.user,role=Membership.Role.PROJECT_MANAGER); self.customer=Customer.objects.create(organization=self.a,legal_name='Projectklant'); self.foreign_customer=Customer.objects.create(organization=self.b,legal_name='Vreemde klant'); self.project=Project.objects.create(organization=self.a,customer=self.customer,name='Eigen project'); self.foreign_project=Project.objects.create(organization=self.b,customer=self.foreign_customer,name='Vreemd project'); self.client.force_login(self.user)
    def test_project_detail_is_tenant_scoped(self): self.assertEqual(self.client.get(reverse('project_detail',args=[self.foreign_project.id])).status_code,404)
    def test_project_manager_can_create_project_for_own_customer(self):
        response=self.client.post(reverse('project_create'),{'customer':self.customer.id,'name':'Nieuw project','status':'active','budget':'1000','members':[self.member.id]}); project=Project.objects.get(name='Nieuw project'); self.assertEqual(project.organization,self.a); self.assertRedirects(response,reverse('project_detail',args=[project.id]))
    def test_time_entry_inherits_tenant_and_requires_own_submit(self):
        self.client.post(reverse('time_entry_add',args=[self.project.id]),{'date':'2026-09-06','hours':'2.50','hourly_rate':'80','description':'Werk'}); entry=TimeEntry.objects.get(project=self.project); self.assertEqual(entry.organization,self.a); self.assertEqual(entry.member,self.member); self.assertRedirects(self.client.post(reverse('time_entry_submit',args=[entry.id])),reverse('project_detail',args=[self.project.id])); entry.refresh_from_db(); self.assertEqual(entry.status,TimeEntry.Status.SUBMITTED)
    def test_central_time_registration_creates_and_lists_entry(self):
        response=self.client.post(reverse('time_entry_create'),{'project':self.project.id,'date':'2026-09-06','hours':'3.25','hourly_rate':'75','description':'Montage'}); self.assertRedirects(response,reverse('time_entry_list')); entry=TimeEntry.objects.get(description='Montage'); self.assertEqual(entry.member,self.member); self.assertEqual(entry.organization,self.a); page=self.client.get(reverse('time_entry_list')); self.assertContains(page,'Montage'); self.assertContains(page,'Eigen project')
    def test_only_time_registration_menu_is_active_on_overview(self):
        page=self.client.get(reverse('time_entry_list')); self.assertContains(page,'class="active" href="/uren/"',html=False); self.assertNotContains(page,'class="active" href="/projecten/"',html=False)
    def test_central_time_registration_rejects_foreign_project(self):
        response=self.client.post(reverse('time_entry_create'),{'project':self.foreign_project.id,'date':'2026-09-06','hours':'1','hourly_rate':'75','description':'Verborgen'}); self.assertEqual(response.status_code,200); self.assertFalse(TimeEntry.objects.filter(description='Verborgen').exists())
    def test_central_time_actions_return_to_overview(self):
        entry=TimeEntry.objects.create(project=self.project,member=self.member,date=date.today(),hours=1,hourly_rate=50,description='Controle'); response=self.client.post(reverse('time_entry_submit',args=[entry.id]),{'next':'time_entry_list'}); self.assertRedirects(response,reverse('time_entry_list')); entry.refresh_from_db(); self.assertEqual(entry.status,TimeEntry.Status.SUBMITTED); response=self.client.post(reverse('time_entry_approve',args=[entry.id]),{'next':'time_entry_list'}); self.assertRedirects(response,reverse('time_entry_list')); entry.refresh_from_db(); self.assertEqual(entry.status,TimeEntry.Status.APPROVED)
    def test_project_manager_cannot_create_sales_opportunity(self):
        response=self.client.post(reverse('opportunity_create'),{'customer':self.customer.id,'title':'Niet toegestaan','stage':'lead','expected_revenue':'100','probability':'10'}); self.assertRedirects(response,reverse('dashboard')); self.assertFalse(Opportunity.objects.exists())

class FinancialAutomationTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Financieel',slug='financieel'); self.user=User.objects.create_user(email='finance-test@example.nl',display_name='Finance',password='CorrectHorseBattery!1'); Membership.objects.create(organization=self.org,user=self.user,role=Membership.Role.OWNER); self.customer=Customer.objects.create(organization=self.org,legal_name='Abonnement BV',email='debiteur@example.nl')
    def test_recurring_schedule_generates_one_draft_and_advances(self):
        schedule=RecurringInvoiceSchedule.objects.create(organization=self.org,customer=self.customer,title='Abonnement',frequency='monthly',next_run=date.today(),payment_term_days=14,lines=[{'description':'Dienst','quantity':'1','unit':'maand','unit_price':'100','vat_rate':21}],created_by=self.user)
        self.assertEqual(len(generate_recurring_drafts(date.today())),1); self.assertEqual(len(generate_recurring_drafts(date.today())),0); schedule.refresh_from_db(); self.assertGreater(schedule.next_run,date.today()); self.assertEqual(Invoice.objects.get().status,Invoice.Status.DRAFT)
    def test_reminder_is_queued_once_at_matching_level(self):
        ReminderPolicy.objects.create(organization=self.org,enabled=True,first_after_days=1,second_after_days=7,final_after_days=14); invoice=Invoice.objects.create(organization=self.org,customer=self.customer,created_by=self.user,number='FAC-1',status=Invoice.Status.SENT,title='Test',issue_date=date.today()-timedelta(days=20),delivery_date=date.today()-timedelta(days=20),due_date=date.today()-timedelta(days=15)); InvoiceLine.objects.create(organization=self.org,invoice=invoice,description='Werk',quantity=1,unit_price=100,vat_rate=21)
        self.assertEqual(len(queue_payment_reminders(date.today())),1); self.assertEqual(len(queue_payment_reminders(date.today())),0); self.assertEqual(PaymentReminder.objects.get().level,3)
    def test_bookkeeping_export_is_zip_and_tenant_scoped(self):
        other=Organization.objects.create(name='Ander',slug='ander-fin'); other_customer=Customer.objects.create(organization=other,legal_name='Geheim'); other_user=User.objects.create_user(email='other-fin@example.nl',display_name='Ander',password='CorrectHorseBattery!1'); invoice=Invoice.objects.create(organization=other,customer=other_customer,created_by=other_user,number='GEHEIM-1',status=Invoice.Status.SENT,title='Geheim',issue_date=date.today(),delivery_date=date.today(),due_date=date.today()); InvoiceLine.objects.create(organization=other,invoice=invoice,description='Geheim',quantity=1,unit_price=99)
        self.client.force_login(self.user); response=self.client.get(reverse('bookkeeping_export'),{'start':date.today().isoformat(),'end':date.today().isoformat()}); self.assertEqual(response.status_code,200); self.assertEqual(response['Content-Type'],'application/zip'); self.assertNotIn(b'GEHEIM-1',response.content)

class PortalSecurityTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Portaalbedrijf',slug='portaalbedrijf'); self.user=User.objects.create_user(email='portal-owner@example.nl',display_name='Owner',password='CorrectHorseBattery!1'); Membership.objects.create(organization=self.org,user=self.user,role=Membership.Role.OWNER); self.customer=Customer.objects.create(organization=self.org,legal_name='Portaalklant',email='klant@example.nl'); self.contact=Contact.objects.create(organization=self.org,customer=self.customer,first_name='Klant'); self.quote=Quote.objects.create(organization=self.org,customer=self.customer,created_by=self.user,number='OFF-1',status=Quote.Status.SENT,title='Voorstel',issue_date=date.today(),valid_until=date.today()+timedelta(days=30)); QuoteLine.objects.create(organization=self.org,quote=self.quote,description='Werk',quantity=1,unit_price=100)
    def test_valid_token_opens_only_linked_customer_and_records_decision(self):
        import hashlib
        token='veilig-test-token'; access=PortalAccess.objects.create(organization=self.org,customer=self.customer,contact=self.contact,token_digest=hashlib.sha256(token.encode()).hexdigest(),token_hint='st-token',expires_at=timezone.now()+timedelta(days=1),created_by=self.user)
        self.assertRedirects(self.client.get(reverse('portal_token',args=[token])),reverse('portal_home')); response=self.client.get(reverse('portal_home')); self.assertContains(response,'OFF-1'); self.assertNotContains(response,'interne notities')
        self.assertRedirects(self.client.post(reverse('portal_quote_decide',args=[self.quote.id]),{'decision':'accepted','signer_name':'Klant Naam'}),reverse('portal_home')); self.quote.refresh_from_db(); decision=PortalDecision.objects.get(quote=self.quote); self.assertEqual(self.quote.status,Quote.Status.ACCEPTED); self.assertEqual(len(decision.document_sha256),64); self.assertEqual(decision.portal_access,access)
    def test_expired_or_revoked_token_is_rejected(self):
        import hashlib
        token='verlopen'; PortalAccess.objects.create(organization=self.org,customer=self.customer,contact=self.contact,token_digest=hashlib.sha256(token.encode()).hexdigest(),token_hint='verlopen',expires_at=timezone.now()-timedelta(seconds=1),created_by=self.user); self.assertEqual(self.client.get(reverse('portal_token',args=[token])).status_code,403)

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
        self.quote.status=Quote.Status.SUBMITTED; self.quote.save(); self.client.force_login(self.approver); self.client.post(reverse('quote_approve',args=[self.quote.id])); self.quote.refresh_from_db(); self.assertEqual(self.quote.status,Quote.Status.APPROVED); self.assertRegex(self.quote.number,r'^OFF-\d{4}-0001$'); self.assertTrue(AuditEvent.objects.filter(action='quote.approved',target_id=str(self.quote.id)).exists())
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
        self.approve(); self.assertEqual(self.invoice.number,f'FAC-{date.today().year}-0001'); self.assertEqual(self.invoice.customer_name_snapshot,'Klant Factuur B.V.'); self.assertEqual(self.invoice.status,Invoice.Status.APPROVED)
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

class ExtensionSecurityTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name='Uitbreiding A',slug='ext-a'); self.other=Organization.objects.create(name='Uitbreiding B',slug='ext-b'); self.owner=User.objects.create_user(email='ext-owner@example.nl',display_name='Eigenaar',password='CorrectHorseBattery!1'); self.worker=User.objects.create_user(email='ext-worker@example.nl',display_name='Werker',password='CorrectHorseBattery!1'); self.member=Membership.objects.create(organization=self.org,user=self.owner,role=Membership.Role.OWNER); Membership.objects.create(organization=self.org,user=self.worker,role=Membership.Role.EMPLOYEE); self.customer=Customer.objects.create(organization=self.org,legal_name='Klant A',email='klant@example.nl'); self.foreign_customer=Customer.objects.create(organization=self.other,legal_name='Klant B'); self.client.force_login(self.owner)
    def test_contract_crud_is_tenant_scoped(self):
        response=self.client.post(reverse('contract_create'),{'customer':self.customer.id,'title':'Onderhoud','status':'active','start_date':date.today(),'notice_days':30,'value':'1200','terms':'Voorwaarden'}); self.assertEqual(response.status_code,302); contract=Contract.objects.get(organization=self.org); self.assertEqual(contract.title,'Onderhoud'); foreign=Contract.objects.create(organization=self.other,customer=self.foreign_customer,title='Verborgen',start_date=date.today()); self.assertEqual(self.client.get(reverse('contract_edit',args=[foreign.id])).status_code,404)
    def test_stock_movement_is_atomic_and_tenant_scoped(self):
        product=Product.objects.create(organization=self.org,code='STK',name='Voorraad',track_stock=True,stock_quantity=5,minimum_stock=2); self.client.post(reverse('stock_movement'),{'product':product.id,'kind':'out','quantity':'3','reason':'Werkbon'}); product.refresh_from_db(); self.assertEqual(product.stock_quantity,Decimal('2')); self.assertTrue(StockMovement.objects.filter(product=product,organization=self.org).exists())
    def test_employee_cannot_access_financial_extensions(self):
        self.client.force_login(self.worker); self.assertRedirects(self.client.get(reverse('inventory')),reverse('dashboard')); self.assertRedirects(self.client.get(reverse('bank_import')),reverse('dashboard')); self.assertRedirects(self.client.get(reverse('integration_list')),reverse('dashboard'))
    def test_signature_is_one_time_and_records_evidence(self):
        contract=Contract.objects.create(organization=self.org,customer=self.customer,title='Tekenbaar',start_date=date.today(),terms='Akkoord'); self.client.post(reverse('signature_create'),{'contract':contract.id,'email':'tekenaar@example.nl'}); item=SignatureRequest.objects.get(contract=contract); token=self.client.session['signature_token'].rsplit('/',2)[-2]; self.client.logout(); response=self.client.post(reverse('signature_public',args=[token]),{'name':'Tekenaar Naam','decision':'signed'},HTTP_USER_AGENT='Testbrowser',REMOTE_ADDR='127.0.0.1'); self.assertContains(response,'Keuze vastgelegd'); item.refresh_from_db(); self.assertEqual(item.status,'signed'); self.assertEqual(item.ip_address,'127.0.0.1'); self.assertEqual(self.client.get(reverse('signature_public',args=[token])).status_code,410)
    def test_api_token_cannot_cross_tenants(self):
        endpoint=IntegrationEndpoint(organization=self.org,kind='import',name='API',enabled=True); endpoint.set_secret('api-secret'); endpoint.save(); response=self.client.get(reverse('api_customers'),HTTP_AUTHORIZATION='Bearer api-secret'); self.assertEqual(response.status_code,200); names=[x['name'] for x in response.json()['results']]; self.assertIn('Klant A',names); self.assertNotIn('Klant B',names); self.assertEqual(self.client.get(reverse('api_customers'),HTTP_AUTHORIZATION='Bearer fout').status_code,401)
    def test_incoming_communication_api_links_customer(self):
        endpoint=IntegrationEndpoint(organization=self.org,kind='import',name='Mailbox',enabled=True); endpoint.set_secret('mail-secret'); endpoint.save(); payload={'customer_id':str(self.customer.id),'subject':'Antwoord','body':'Binnengekomen','sender':'klant@example.nl','recipient':'info@example.nl'}; response=self.client.post(reverse('api_communications'),data=json.dumps(payload),content_type='application/json',HTTP_AUTHORIZATION='Bearer mail-secret'); self.assertEqual(response.status_code,201); self.assertTrue(Communication.objects.filter(organization=self.org,direction='in',status='received').exists())
    def test_bank_import_is_idempotent_and_matches_exact_invoice(self):
        invoice=Invoice.objects.create(organization=self.org,customer=self.customer,created_by=self.owner,number='FAC-2026-0042',status=Invoice.Status.SENT,issue_date=date.today(),delivery_date=date.today(),due_date=date.today()); InvoiceLine.objects.create(organization=self.org,invoice=invoice,description='Werk',quantity=1,unit_price=100,vat_rate=0); content=f'datum;bedrag;omschrijving\n{date.today().isoformat()};100,00;Betaling FAC-2026-0042\n'.encode()
        for _ in range(2): self.client.post(reverse('bank_import'),{'file':SimpleUploadedFile('bank.csv',content)})
        self.assertEqual(BankTransaction.objects.filter(organization=self.org).count(),1); self.assertEqual(Payment.objects.filter(invoice=invoice).count(),1)
    def test_monitoring_deduplicates_open_alerts(self):
        Product.objects.create(organization=self.org,code='LOW',name='Laag',track_stock=True,stock_quantity=0,minimum_stock=2); refresh_system_alerts(); refresh_system_alerts(); self.assertEqual(SystemAlert.objects.filter(organization=self.org,code='low_stock',is_resolved=False).count(),1)
    def test_pwa_assets_are_served(self):
        response=self.client.get(reverse('service_worker')); self.assertEqual(response.status_code,200); self.assertEqual(response['Service-Worker-Allowed'],'/')
    def test_camt_and_mt940_are_parsed(self):
        camt='<?xml version="1.0"?><Document><Ntry><Amt>12.34</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-09-06</Dt></BookgDt><AddtlNtryInf>FAC-1</AddtlNtryInf></Ntry></Document>'; mt940=':20:START\n:61:260906C99,95NTRF\n:86:Betaling FAC-2'
        self.assertEqual(_parse_bank_rows(camt)[0]['bedrag'],'12.34'); self.assertEqual(_parse_bank_rows(mt940)[0]['bedrag'],'99,95'); self.assertEqual(_parse_bank_rows(mt940)[0]['datum'],'2026-09-06')
    def test_document_template_layout_is_saved(self):
        response=self.client.post(reverse('template_create'),{'kind':'invoice','name':'Modern','header':'Kop','footer':'Voet','primary_color':'#123456','is_default':'on','layout_order':'header,lines,totals,footer'}); self.assertRedirects(response,reverse('template_list')); item=DocumentTemplate.objects.get(organization=self.org); self.assertEqual(item.layout,['header','lines','totals','footer']); self.assertTrue(item.is_default)
    def test_mollie_webhook_books_payment_only_once(self):
        invoice=Invoice.objects.create(organization=self.org,customer=self.customer,created_by=self.owner,number='FAC-MOL',status=Invoice.Status.SENT,issue_date=date.today(),delivery_date=date.today(),due_date=date.today()); InvoiceLine.objects.create(organization=self.org,invoice=invoice,description='Werk',quantity=1,unit_price=25,vat_rate=0); integration=IntegrationEndpoint(organization=self.org,kind='mollie',name='Mollie',enabled=True); integration.set_secret('test_x'); integration.save(); link=PaymentLink.objects.create(organization=self.org,invoice=invoice,provider_id='tr_test',amount=25,status='open',created_by=self.owner)
        fake=type('Response',(),{'read':lambda self:b'{"status":"paid"}'})()
        with patch('core.extensions.urllib.request.urlopen',return_value=fake): self.client.post(reverse('mollie_webhook'),{'id':'tr_test'}); self.client.post(reverse('mollie_webhook'),{'id':'tr_test'})
        link.refresh_from_db(); self.assertEqual(link.status,'paid'); self.assertEqual(Payment.objects.filter(invoice=invoice,reference='Mollie tr_test').count(),1)
