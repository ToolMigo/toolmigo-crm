import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    use_in_migrations=True
    def create_user(self,email,password=None,**extra_fields):
        if not email: raise ValueError('Een e-mailadres is verplicht.')
        email=self.normalize_email(email).lower()
        user=self.model(email=email,**extra_fields); user.set_password(password); user.save(using=self._db); return user
    def create_superuser(self,email,password=None,**extra_fields):
        extra_fields.setdefault('is_staff',True); extra_fields.setdefault('is_superuser',True); extra_fields.setdefault('is_active',True); extra_fields.setdefault('is_platform_admin',True)
        if extra_fields.get('is_staff') is not True or extra_fields.get('is_superuser') is not True: raise ValueError('Een superuser moet staff- en superuserrechten hebben.')
        return self.create_user(email,password,**extra_fields)

class User(AbstractUser):
    class Theme(models.TextChoices): SYSTEM='system','Systeeminstelling'; LIGHT='light','Light mode'; DARK='dark','Dark mode'
    username = None
    email = models.EmailField('e-mailadres', unique=True)
    display_name = models.CharField('naam', max_length=150)
    is_platform_admin = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='profiles/avatars/',blank=True)
    theme_preference = models.CharField(max_length=10,choices=Theme.choices,default=Theme.SYSTEM)
    totp_secret_encrypted = models.TextField(blank=True)
    totp_enabled = models.BooleanField(default=False)
    recovery_code_hashes = models.JSONField(default=list,blank=True)
    objects=UserManager()
    USERNAME_FIELD='email'; REQUIRED_FIELDS=['display_name']
    def __str__(self): return self.display_name or self.email
    def set_totp_secret(self,value):
        from .encryption import encrypt_secret
        self.totp_secret_encrypted=encrypt_secret(value) if value else ''
    def get_totp_secret(self):
        from .encryption import decrypt_secret
        return decrypt_secret(self.totp_secret_encrypted) if self.totp_secret_encrypted else ''

class Organization(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=180)
    slug=models.SlugField(max_length=80,unique=True)
    kvk_number=models.CharField(max_length=20,blank=True)
    vat_id=models.CharField(max_length=32,blank=True)
    iban=models.CharField(max_length=34,blank=True)
    address=models.CharField(max_length=200,blank=True)
    postal_code=models.CharField(max_length=12,blank=True)
    city=models.CharField(max_length=100,blank=True)
    payment_term_days=models.PositiveSmallIntegerField(default=14)
    logo=models.ImageField(upload_to='organizations/logos/',blank=True)
    primary_color=models.CharField(max_length=7,default='#239f7f')
    quote_prefix=models.CharField(max_length=10,default='OFF')
    invoice_prefix=models.CharField(max_length=10,default='FAC')
    quote_valid_days=models.PositiveSmallIntegerField(default=30)
    default_quote_terms=models.TextField(blank=True)
    default_invoice_notes=models.TextField(blank=True)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class OrganizationEmailSettings(models.Model):
    organization=models.OneToOneField(Organization,on_delete=models.CASCADE,related_name='email_settings')
    host=models.CharField(max_length=255)
    port=models.PositiveIntegerField(default=587)
    username=models.CharField(max_length=255,blank=True)
    password_encrypted=models.TextField(blank=True)
    from_email=models.EmailField()
    use_tls=models.BooleanField(default=True)
    use_ssl=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    updated_at=models.DateTimeField(auto_now=True)
    def set_password(self,value):
        from .encryption import encrypt_secret
        self.password_encrypted=encrypt_secret(value) if value else ''
    def get_password(self):
        from .encryption import decrypt_secret
        return decrypt_secret(self.password_encrypted) if self.password_encrypted else ''
    def __str__(self): return f'SMTP · {self.organization}'

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER='owner','Bedrijfsbeheerder'
        BILLING='approver','Facturatie'
        EMPLOYEE='employee','Medewerker'
        SALES='sales','Verkoop'
        CUSTOMER_MANAGER='customer_manager','Klantbeheer'
        PLANNER='planner','Planning'
        PROJECT_MANAGER='project_manager','Projectbeheer'
        SUPPORT='support','Support'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='memberships')
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='memberships')
    role=models.CharField(max_length=20,choices=Role.choices,default=Role.EMPLOYEE)
    is_active=models.BooleanField(default=True)
    is_removed=models.BooleanField(default=False,db_index=True)
    removed_at=models.DateTimeField(null=True,blank=True)
    removed_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='removed_memberships')
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['organization','user'],name='unique_org_membership')]
    def __str__(self): return f'{self.user} · {self.organization} · {self.get_role_display()}'

class AuditEvent(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='audit_events',null=True,blank=True)
    actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='audit_events')
    action=models.CharField(max_length=100)
    target_type=models.CharField(max_length=80,blank=True)
    target_id=models.CharField(max_length=100,blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    ip_address=models.GenericIPAddressField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True,db_index=True)
    class Meta: ordering=['-created_at']
    def __str__(self): return f'{self.created_at} {self.action}'

class Customer(models.Model):
    class Kind(models.TextChoices): COMPANY='company','Bedrijf'; PERSON='person','Particulier'
    class Status(models.TextChoices): LEAD='lead','Lead'; ACTIVE='active','Actief'; INACTIVE='inactive','Inactief'; ARCHIVED='archived','Gearchiveerd'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='customers')
    kind=models.CharField(max_length=12,choices=Kind.choices,default=Kind.COMPANY)
    legal_name=models.CharField('naam',max_length=200)
    trade_name=models.CharField('handelsnaam',max_length=200,blank=True)
    email=models.EmailField(blank=True); phone=models.CharField(max_length=40,blank=True)
    kvk_number=models.CharField('KvK-nummer',max_length=20,blank=True)
    vat_id=models.CharField('btw-identificatienummer',max_length=32,blank=True)
    address=models.CharField('straat en huisnummer',max_length=200,blank=True)
    postal_code=models.CharField('postcode',max_length=12,blank=True)
    city=models.CharField('plaats',max_length=100,blank=True)
    billing_address=models.CharField('afwijkend factuuradres',max_length=200,blank=True)
    billing_postal_code=models.CharField('factuurpostcode',max_length=12,blank=True)
    billing_city=models.CharField('factuurplaats',max_length=100,blank=True)
    payment_term_days=models.PositiveSmallIntegerField('betalingstermijn',default=14)
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.ACTIVE,db_index=True)
    labels=models.JSONField(default=list,blank=True)
    owner=models.ForeignKey(Membership,on_delete=models.SET_NULL,null=True,blank=True,related_name='owned_customers')
    notes=models.TextField('interne notities',blank=True)
    archived_at=models.DateTimeField(null=True,blank=True)
    archived_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='archived_customers')
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['legal_name']; indexes=[models.Index(fields=['organization','status']),models.Index(fields=['organization','legal_name'])]
        constraints=[models.UniqueConstraint(fields=['organization','kvk_number'],condition=~models.Q(kvk_number=''),name='unique_org_kvk')]
    def __str__(self): return self.trade_name or self.legal_name

class Contact(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='contacts')
    customer=models.ForeignKey(Customer,on_delete=models.CASCADE,related_name='contacts')
    first_name=models.CharField('voornaam',max_length=100); last_name=models.CharField('achternaam',max_length=120,blank=True)
    job_title=models.CharField('functie',max_length=120,blank=True); email=models.EmailField(blank=True); phone=models.CharField(max_length=40,blank=True)
    is_primary=models.BooleanField('primair contact',default=False); is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-is_primary','first_name','last_name']
    def __str__(self): return f'{self.first_name} {self.last_name}'.strip()
    def save(self,*args,**kwargs):
        self.organization_id=self.customer.organization_id
        super().save(*args,**kwargs)
        if self.is_primary: Contact.objects.filter(customer=self.customer,is_primary=True).exclude(pk=self.pk).update(is_primary=False)

class CustomerActivity(models.Model):
    class Kind(models.TextChoices): NOTE='note','Notitie'; SYSTEM='system','Systeem'; EMAIL='email','E-mail'; CALL='call','Telefoongesprek'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='customer_activities')
    customer=models.ForeignKey(Customer,on_delete=models.CASCADE,related_name='activities')
    actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True)
    kind=models.CharField(max_length=15,choices=Kind.choices,default=Kind.NOTE)
    body=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

MONEY_PLACES=Decimal('0.01')
def money(value): return Decimal(value or 0).quantize(MONEY_PLACES,rounding=ROUND_HALF_UP)

class Product(models.Model):
    class Kind(models.TextChoices): SERVICE='service','Dienst'; PRODUCT='product','Product'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='products')
    code=models.CharField(max_length=40); name=models.CharField(max_length=180); description=models.TextField(blank=True)
    kind=models.CharField(max_length=12,choices=Kind.choices,default=Kind.SERVICE)
    unit=models.CharField(max_length=30,default='stuk'); unit_price=models.DecimalField(max_digits=12,decimal_places=2,default=0)
    vat_rate=models.DecimalField(max_digits=5,decimal_places=2,default=21)
    is_active=models.BooleanField(default=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['name']; constraints=[models.UniqueConstraint(fields=['organization','code'],name='unique_org_product_code')]
    def __str__(self): return f'{self.code} · {self.name}'

class DocumentSequence(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='sequences')
    document_type=models.CharField(max_length=20); year=models.PositiveSmallIntegerField(); next_number=models.PositiveIntegerField(default=1)
    class Meta: constraints=[models.UniqueConstraint(fields=['organization','document_type','year'],name='unique_document_sequence')]

class Quote(models.Model):
    class Status(models.TextChoices): DRAFT='draft','Concept'; SUBMITTED='submitted','Ter goedkeuring'; APPROVED='approved','Goedgekeurd'; REJECTED='rejected','Afgewezen'; SENT='sent','Verzonden'; ACCEPTED='accepted','Geaccepteerd'; DECLINED='declined','Afgewezen door klant'; EXPIRED='expired','Verlopen'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='quotes')
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='quotes')
    created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='created_quotes')
    approved_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='approved_quotes')
    number=models.CharField(max_length=30,blank=True); status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT,db_index=True)
    title=models.CharField(max_length=200,default='Offerte'); issue_date=models.DateField(); valid_until=models.DateField()
    introduction=models.TextField(blank=True); terms=models.TextField(blank=True); internal_notes=models.TextField(blank=True)
    rejection_reason=models.TextField(blank=True); approved_at=models.DateTimeField(null=True,blank=True); submitted_at=models.DateTimeField(null=True,blank=True)
    is_archived=models.BooleanField(default=False,db_index=True); archived_at=models.DateTimeField(null=True,blank=True); archived_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='archived_quotes')
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['-created_at']; constraints=[models.UniqueConstraint(fields=['organization','number'],condition=~models.Q(number=''),name='unique_org_quote_number')]
    def __str__(self): return self.number or f'Concept {str(self.id)[:8]}'
    @property
    def subtotal(self): return money(sum((line.net_amount for line in self.lines.all()),Decimal('0')))
    @property
    def vat_total(self): return money(sum((line.vat_amount for line in self.lines.all()),Decimal('0')))
    @property
    def total(self): return money(self.subtotal+self.vat_total)

class QuoteLine(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='quote_lines')
    quote=models.ForeignKey(Quote,on_delete=models.CASCADE,related_name='lines')
    product=models.ForeignKey(Product,on_delete=models.SET_NULL,null=True,blank=True,related_name='quote_lines')
    position=models.PositiveSmallIntegerField(default=1); description=models.TextField(); quantity=models.DecimalField(max_digits=10,decimal_places=2,default=1)
    unit=models.CharField(max_length=30,default='stuk'); unit_price=models.DecimalField(max_digits=12,decimal_places=2); discount_percent=models.DecimalField(max_digits=5,decimal_places=2,default=0); vat_rate=models.DecimalField(max_digits=5,decimal_places=2,default=21)
    class Meta: ordering=['position','id']
    def save(self,*args,**kwargs): self.organization_id=self.quote.organization_id; super().save(*args,**kwargs)
    @property
    def gross_amount(self): return money(Decimal(str(self.quantity))*Decimal(str(self.unit_price)))
    @property
    def net_amount(self): return money(self.gross_amount*(Decimal('1')-Decimal(str(self.discount_percent))/Decimal('100')))
    @property
    def vat_amount(self): return money(self.net_amount*Decimal(str(self.vat_rate))/Decimal('100'))
    @property
    def total_amount(self): return money(self.net_amount+self.vat_amount)

class Invoice(models.Model):
    class Kind(models.TextChoices): INVOICE='invoice','Factuur'; CREDIT='credit','Creditfactuur'
    class Status(models.TextChoices): DRAFT='draft','Concept'; SUBMITTED='submitted','Ter goedkeuring'; APPROVED='approved','Goedgekeurd'; REJECTED='rejected','Afgewezen'; QUEUED='queued','Klaar voor verzending'; SENT='sent','Verzonden'; PARTIAL='partial','Deels betaald'; PAID='paid','Betaald'; OVERDUE='overdue','Vervallen'; CREDITED='credited','Gecrediteerd'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='invoices')
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='invoices')
    source_quote=models.OneToOneField(Quote,on_delete=models.SET_NULL,null=True,blank=True,related_name='invoice')
    original_invoice=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True,related_name='credit_invoices')
    created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='created_invoices'); approved_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='approved_invoices')
    kind=models.CharField(max_length=10,choices=Kind.choices,default=Kind.INVOICE); number=models.CharField(max_length=30,blank=True); status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT,db_index=True)
    title=models.CharField(max_length=200,default='Factuur'); issue_date=models.DateField(); due_date=models.DateField(); delivery_date=models.DateField()
    notes=models.TextField(blank=True); payment_reference=models.CharField(max_length=50,blank=True); rejection_reason=models.TextField(blank=True)
    customer_name_snapshot=models.CharField(max_length=200,blank=True); customer_address_snapshot=models.CharField(max_length=300,blank=True); customer_vat_snapshot=models.CharField(max_length=32,blank=True)
    submitted_at=models.DateTimeField(null=True,blank=True); approved_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True)
    is_archived=models.BooleanField(default=False,db_index=True); archived_at=models.DateTimeField(null=True,blank=True); archived_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='archived_invoices')
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-created_at']; constraints=[models.UniqueConstraint(fields=['organization','number'],condition=~models.Q(number=''),name='unique_org_invoice_number')]
    def __str__(self): return self.number or f'Concept {str(self.id)[:8]}'
    @property
    def subtotal(self): return money(sum((x.net_amount for x in self.lines.all()),Decimal('0')))
    @property
    def vat_total(self): return money(sum((x.vat_amount for x in self.lines.all()),Decimal('0')))
    @property
    def total(self): return money(self.subtotal+self.vat_total)
    @property
    def paid_amount(self): return money(sum((x.amount for x in self.payments.all()),Decimal('0')))
    @property
    def outstanding(self): return money(self.total-self.paid_amount)

class InvoiceLine(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='invoice_lines'); invoice=models.ForeignKey(Invoice,on_delete=models.CASCADE,related_name='lines')
    position=models.PositiveSmallIntegerField(default=1); description=models.TextField(); quantity=models.DecimalField(max_digits=10,decimal_places=2,default=1); unit=models.CharField(max_length=30,default='stuk'); unit_price=models.DecimalField(max_digits=12,decimal_places=2); discount_percent=models.DecimalField(max_digits=5,decimal_places=2,default=0); vat_rate=models.DecimalField(max_digits=5,decimal_places=2,default=21)
    class Meta: ordering=['position','id']
    def save(self,*args,**kwargs): self.organization_id=self.invoice.organization_id; super().save(*args,**kwargs)
    @property
    def gross_amount(self): return money(Decimal(str(self.quantity))*Decimal(str(self.unit_price)))
    @property
    def net_amount(self): return money(self.gross_amount*(Decimal('1')-Decimal(str(self.discount_percent))/Decimal('100')))
    @property
    def vat_amount(self): return money(self.net_amount*Decimal(str(self.vat_rate))/Decimal('100'))

class Payment(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='payments'); invoice=models.ForeignKey(Invoice,on_delete=models.PROTECT,related_name='payments'); amount=models.DecimalField(max_digits=12,decimal_places=2); paid_on=models.DateField(); reference=models.CharField(max_length=120,blank=True); recorded_by=models.ForeignKey(User,on_delete=models.PROTECT); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-paid_on','-created_at']
    def save(self,*args,**kwargs): self.organization_id=self.invoice.organization_id; super().save(*args,**kwargs)

class EmailDelivery(models.Model):
    class Status(models.TextChoices): QUEUED='queued','In wachtrij'; SENT='sent','Verzonden'; FAILED='failed','Mislukt'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='email_deliveries'); document_type=models.CharField(max_length=20); document_id=models.UUIDField(); recipient=models.EmailField(); subject=models.CharField(max_length=250); status=models.CharField(max_length=12,choices=Status.choices,default=Status.QUEUED); error=models.TextField(blank=True); requested_by=models.ForeignKey(User,on_delete=models.PROTECT); created_at=models.DateTimeField(auto_now_add=True); sent_at=models.DateTimeField(null=True,blank=True); is_archived=models.BooleanField(default=False,db_index=True); archived_at=models.DateTimeField(null=True,blank=True); archived_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='archived_email_deliveries')
    class Meta: ordering=['-created_at']; indexes=[models.Index(fields=['organization','status'])]

class AppointmentType(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='appointment_types'); name=models.CharField(max_length=100); color=models.CharField(max_length=7,default='#239F7F'); is_active=models.BooleanField(default=True)
    class Meta: ordering=['name']; constraints=[models.UniqueConstraint(fields=['organization','name'],name='unique_org_appointment_type')]
    def __str__(self): return self.name

class Appointment(models.Model):
    class Recurrence(models.TextChoices): NONE='none','Niet herhalen'; DAILY='daily','Dagelijks'; WEEKLY='weekly','Wekelijks'; MONTHLY='monthly','Maandelijks'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='appointments'); title=models.CharField(max_length=180); appointment_type=models.ForeignKey(AppointmentType,on_delete=models.SET_NULL,null=True,blank=True,related_name='appointments'); customer=models.ForeignKey(Customer,on_delete=models.SET_NULL,null=True,blank=True,related_name='appointments'); participants=models.ManyToManyField(Membership,related_name='appointments')
    start=models.DateTimeField(db_index=True); end=models.DateTimeField(db_index=True); all_day=models.BooleanField(default=False); location=models.CharField(max_length=200,blank=True); description=models.TextField(blank=True); reminder_minutes=models.PositiveIntegerField(default=30)
    recurrence=models.CharField(max_length=10,choices=Recurrence.choices,default=Recurrence.NONE); recurrence_until=models.DateField(null=True,blank=True); series_id=models.UUIDField(default=uuid.uuid4,db_index=True); is_cancelled=models.BooleanField(default=False); created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='created_appointments'); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['start']; indexes=[models.Index(fields=['organization','start','end'])]
    def __str__(self): return self.title

class Board(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='boards'); name=models.CharField(max_length=120); is_default=models.BooleanField(default=False); is_archived=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['name']; constraints=[models.UniqueConstraint(fields=['organization','name'],name='unique_org_board')]
    def __str__(self): return self.name

class BoardColumn(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='board_columns'); board=models.ForeignKey(Board,on_delete=models.CASCADE,related_name='columns'); name=models.CharField(max_length=80); position=models.PositiveSmallIntegerField(default=1); color=models.CharField(max_length=7,default='#239F7F'); is_done=models.BooleanField(default=False)
    class Meta: ordering=['position','id']; constraints=[models.UniqueConstraint(fields=['board','name'],name='unique_board_column')]
    def save(self,*args,**kwargs): self.organization_id=self.board.organization_id; super().save(*args,**kwargs)
    def __str__(self): return self.name

class Task(models.Model):
    class Priority(models.TextChoices): LOW='low','Laag'; NORMAL='normal','Normaal'; HIGH='high','Hoog'; URGENT='urgent','Urgent'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='tasks'); board=models.ForeignKey(Board,on_delete=models.CASCADE,related_name='tasks'); column=models.ForeignKey(BoardColumn,on_delete=models.PROTECT,related_name='tasks'); title=models.CharField(max_length=200); description=models.TextField(blank=True); priority=models.CharField(max_length=10,choices=Priority.choices,default=Priority.NORMAL); position=models.PositiveIntegerField(default=1); due_date=models.DateTimeField(null=True,blank=True,db_index=True); labels=models.JSONField(default=list,blank=True)
    assignees=models.ManyToManyField(Membership,related_name='tasks'); customer=models.ForeignKey(Customer,on_delete=models.SET_NULL,null=True,blank=True,related_name='tasks'); quote=models.ForeignKey(Quote,on_delete=models.SET_NULL,null=True,blank=True,related_name='tasks'); invoice=models.ForeignKey(Invoice,on_delete=models.SET_NULL,null=True,blank=True,related_name='tasks'); appointment=models.ForeignKey(Appointment,on_delete=models.SET_NULL,null=True,blank=True,related_name='tasks')
    created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='created_tasks'); completed_at=models.DateTimeField(null=True,blank=True); is_archived=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['position','created_at']; indexes=[models.Index(fields=['organization','due_date']),models.Index(fields=['board','column','position'])]
    def save(self,*args,**kwargs): self.organization_id=self.board.organization_id; super().save(*args,**kwargs)
    def __str__(self): return self.title

class TaskChecklistItem(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='checklist_items'); task=models.ForeignKey(Task,on_delete=models.CASCADE,related_name='checklist'); text=models.CharField(max_length=240); position=models.PositiveSmallIntegerField(default=1); is_done=models.BooleanField(default=False); completed_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['position','id']
    def save(self,*args,**kwargs): self.organization_id=self.task.organization_id; super().save(*args,**kwargs)

class TaskComment(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='task_comments'); task=models.ForeignKey(Task,on_delete=models.CASCADE,related_name='comments'); author=models.ForeignKey(User,on_delete=models.PROTECT); body=models.TextField(max_length=4000); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']
    def save(self,*args,**kwargs): self.organization_id=self.task.organization_id; super().save(*args,**kwargs)

def task_upload_path(instance,filename): return f'organizations/{instance.task.organization_id}/tasks/{instance.task_id}/{uuid.uuid4().hex}_{filename}'
class TaskAttachment(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='task_attachments'); task=models.ForeignKey(Task,on_delete=models.CASCADE,related_name='attachments'); uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT); file=models.FileField(upload_to=task_upload_path); original_name=models.CharField(max_length=255); content_type=models.CharField(max_length=120,blank=True); size=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now_add=True)
    def save(self,*args,**kwargs): self.organization_id=self.task.organization_id; super().save(*args,**kwargs)

class BackupConfiguration(models.Model):
    class Frequency(models.TextChoices): DAILY='daily','Dagelijks'; WEEKLY='weekly','Wekelijks'
    max_backups=models.PositiveSmallIntegerField(default=10)
    automatic_enabled=models.BooleanField(default=False)
    frequency=models.CharField(max_length=10,choices=Frequency.choices,default=Frequency.DAILY)
    weekday=models.PositiveSmallIntegerField(default=0)
    run_at=models.TimeField(default='02:00')
    last_run_date=models.DateField(null=True,blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    @classmethod
    def load(cls): return cls.objects.get_or_create(pk=1)[0]

class Opportunity(models.Model):
    class Stage(models.TextChoices): LEAD='lead','Lead'; QUALIFIED='qualified','Gekwalificeerd'; PROPOSAL='proposal','Voorstel'; NEGOTIATION='negotiation','Onderhandeling'; WON='won','Gewonnen'; LOST='lost','Verloren'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='opportunities'); customer=models.ForeignKey(Customer,on_delete=models.SET_NULL,null=True,blank=True,related_name='opportunities'); title=models.CharField(max_length=200); stage=models.CharField(max_length=20,choices=Stage.choices,default=Stage.LEAD,db_index=True); expected_revenue=models.DecimalField(max_digits=12,decimal_places=2,default=0); probability=models.PositiveSmallIntegerField(default=10); follow_up_date=models.DateField(null=True,blank=True,db_index=True); owner=models.ForeignKey(Membership,on_delete=models.SET_NULL,null=True,blank=True,related_name='opportunities'); notes=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['follow_up_date','-created_at']; indexes=[models.Index(fields=['organization','stage'])]
    def __str__(self): return self.title

class Project(models.Model):
    class Status(models.TextChoices): PLANNED='planned','Gepland'; ACTIVE='active','Actief'; ON_HOLD='on_hold','Gepauzeerd'; COMPLETED='completed','Afgerond'; CANCELLED='cancelled','Geannuleerd'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='projects'); customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='projects'); name=models.CharField(max_length=200); status=models.CharField(max_length=20,choices=Status.choices,default=Status.PLANNED,db_index=True); budget=models.DecimalField(max_digits=12,decimal_places=2,default=0); start_date=models.DateField(null=True,blank=True); end_date=models.DateField(null=True,blank=True); members=models.ManyToManyField(Membership,blank=True,related_name='projects'); notes=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-created_at']; indexes=[models.Index(fields=['organization','status'])]
    def __str__(self): return self.name

class TimeEntry(models.Model):
    class Status(models.TextChoices): DRAFT='draft','Concept'; SUBMITTED='submitted','Ingediend'; APPROVED='approved','Goedgekeurd'; INVOICED='invoiced','Gefactureerd'; REJECTED='rejected','Afgewezen'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='time_entries'); project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='time_entries'); member=models.ForeignKey(Membership,on_delete=models.PROTECT,related_name='time_entries'); date=models.DateField(); hours=models.DecimalField(max_digits=6,decimal_places=2); hourly_rate=models.DecimalField(max_digits=10,decimal_places=2,default=0); description=models.CharField(max_length=300); status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT,db_index=True); approved_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='approved_time_entries'); invoice=models.ForeignKey(Invoice,on_delete=models.PROTECT,null=True,blank=True,related_name='time_entries'); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-date','-created_at']; indexes=[models.Index(fields=['organization','status'])]
    def save(self,*args,**kwargs): self.organization_id=self.project.organization_id; super().save(*args,**kwargs)
    @property
    def amount(self): return money(self.hours*self.hourly_rate)

class MileageEntry(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='mileage_entries'); project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='mileage_entries'); member=models.ForeignKey(Membership,on_delete=models.PROTECT,related_name='mileage_entries'); date=models.DateField(); kilometers=models.DecimalField(max_digits=8,decimal_places=2); rate=models.DecimalField(max_digits=6,decimal_places=2,default=0.23); description=models.CharField(max_length=300); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-date'];
    def save(self,*args,**kwargs): self.organization_id=self.project.organization_id; super().save(*args,**kwargs)
    @property
    def amount(self): return money(self.kilometers*self.rate)

def expense_upload_path(instance,filename): return f'organizations/{instance.organization_id}/projects/{instance.project_id}/expenses/{uuid.uuid4().hex}_{filename}'
class Expense(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='expenses'); project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='expenses'); member=models.ForeignKey(Membership,on_delete=models.PROTECT,related_name='expenses'); date=models.DateField(); amount=models.DecimalField(max_digits=10,decimal_places=2); description=models.CharField(max_length=300); receipt=models.FileField(upload_to=expense_upload_path,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-date'];
    def save(self,*args,**kwargs): self.organization_id=self.project.organization_id; super().save(*args,**kwargs)

def project_document_path(instance,filename): return f'organizations/{instance.organization_id}/projects/{instance.project_id or "customer"}/documents/{uuid.uuid4().hex}_{filename}'
class ProjectDocument(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='documents'); project=models.ForeignKey(Project,on_delete=models.CASCADE,null=True,blank=True,related_name='documents'); customer=models.ForeignKey(Customer,on_delete=models.CASCADE,null=True,blank=True,related_name='documents'); title=models.CharField(max_length=200); file=models.FileField(upload_to=project_document_path); original_name=models.CharField(max_length=255); content_type=models.CharField(max_length=120,blank=True); size=models.PositiveIntegerField(default=0); uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='uploaded_documents'); visible_to_portal=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']; constraints=[models.CheckConstraint(condition=models.Q(project__isnull=False)|models.Q(customer__isnull=False),name='document_has_parent')]

class RecurringInvoiceSchedule(models.Model):
    class Frequency(models.TextChoices): MONTHLY='monthly','Maandelijks'; QUARTERLY='quarterly','Per kwartaal'; YEARLY='yearly','Jaarlijks'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='recurring_invoice_schedules'); customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='recurring_invoice_schedules'); title=models.CharField(max_length=200); frequency=models.CharField(max_length=12,choices=Frequency.choices,default=Frequency.MONTHLY); next_run=models.DateField(db_index=True); payment_term_days=models.PositiveSmallIntegerField(default=14); lines=models.JSONField(default=list); notes=models.TextField(blank=True); is_active=models.BooleanField(default=True); last_generated_at=models.DateTimeField(null=True,blank=True); created_by=models.ForeignKey(User,on_delete=models.PROTECT); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['next_run']; indexes=[models.Index(fields=['organization','is_active','next_run'])]
    def __str__(self): return self.title

class ReminderPolicy(models.Model):
    organization=models.OneToOneField(Organization,on_delete=models.CASCADE,related_name='reminder_policy'); enabled=models.BooleanField(default=False); first_after_days=models.PositiveSmallIntegerField(default=1); second_after_days=models.PositiveSmallIntegerField(default=7); final_after_days=models.PositiveSmallIntegerField(default=14); updated_at=models.DateTimeField(auto_now=True)

class EmailTemplate(models.Model):
    class Kind(models.TextChoices): QUOTE='quote','Offerte'; INVOICE='invoice','Factuur'; REMINDER1='reminder1','Eerste herinnering'; REMINDER2='reminder2','Tweede herinnering'; REMINDER_FINAL='reminder_final','Laatste herinnering'
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='email_templates'); kind=models.CharField(max_length=20,choices=Kind.choices); subject=models.CharField(max_length=250); body=models.TextField(); updated_at=models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['organization','kind'],name='unique_org_email_template')]

class PaymentReminder(models.Model):
    class Status(models.TextChoices): QUEUED='queued','In wachtrij'; SENT='sent','Verzonden'; FAILED='failed','Mislukt'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='payment_reminders'); invoice=models.ForeignKey(Invoice,on_delete=models.PROTECT,related_name='reminders'); level=models.PositiveSmallIntegerField(); recipient=models.EmailField(); subject=models.CharField(max_length=250); body=models.TextField(); status=models.CharField(max_length=10,choices=Status.choices,default=Status.QUEUED); error=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); sent_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-created_at']; constraints=[models.UniqueConstraint(fields=['invoice','level'],name='unique_invoice_reminder_level')]

class PortalAccess(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='portal_accesses'); customer=models.ForeignKey(Customer,on_delete=models.CASCADE,related_name='portal_accesses'); contact=models.ForeignKey(Contact,on_delete=models.CASCADE,related_name='portal_accesses'); token_digest=models.CharField(max_length=64,unique=True); token_hint=models.CharField(max_length=12); expires_at=models.DateTimeField(db_index=True); revoked_at=models.DateTimeField(null=True,blank=True); created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='created_portal_accesses'); created_at=models.DateTimeField(auto_now_add=True); last_used_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-created_at']; indexes=[models.Index(fields=['organization','customer','expires_at'])]
    @property
    def is_valid(self): return self.revoked_at is None and self.expires_at>timezone.now()

class PortalDecision(models.Model):
    class Decision(models.TextChoices): ACCEPTED='accepted','Geaccepteerd'; DECLINED='declined','Afgewezen'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); organization=models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='portal_decisions'); portal_access=models.ForeignKey(PortalAccess,on_delete=models.PROTECT,related_name='decisions'); quote=models.OneToOneField(Quote,on_delete=models.PROTECT,related_name='portal_decision'); decision=models.CharField(max_length=10,choices=Decision.choices); signer_name=models.CharField(max_length=200); reason=models.TextField(blank=True); document_sha256=models.CharField(max_length=64); ip_address=models.GenericIPAddressField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)
