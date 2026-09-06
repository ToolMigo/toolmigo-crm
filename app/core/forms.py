from django import forms
from decimal import Decimal
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Appointment, AppointmentType, BackupConfiguration, BankTransaction, Board, BoardColumn, CalendarConnection, Communication, Contact, Contract, Customer, DocumentTemplate, EmailTemplate, Expense, IntegrationEndpoint, Invoice, InvoiceLine, Membership, MileageEntry, Opportunity, Organization, OrganizationEmailSettings, Payment, Product, Project, ProjectDocument, Quote, QuoteLine, RecurringInvoiceSchedule, ReminderPolicy, ServiceTicket, StockMovement, Task, TaskAttachment, TimeEntry, User, WorkOrder

class LoginForm(AuthenticationForm):
    username=forms.EmailField(label='E-mailadres',widget=forms.EmailInput(attrs={'autofocus':True,'autocomplete':'email','placeholder':'naam@bedrijf.nl'}))
    password=forms.CharField(label='Wachtwoord',strip=False,widget=forms.PasswordInput(attrs={'autocomplete':'current-password','placeholder':'••••••••••••'}))

class ProfileForm(forms.ModelForm):
    class Meta: model=User; fields=('display_name','email','theme_preference','avatar'); labels={'display_name':'Volledige naam','theme_preference':'Kleurmodus','avatar':'Profielfoto'}
    def clean_email(self): return self.cleaned_data['email'].strip().lower()
    def clean_avatar(self):
        avatar=self.cleaned_data.get('avatar')
        if avatar and getattr(avatar,'size',0)>5*1024*1024: raise forms.ValidationError('De profielfoto is groter dan 5 MB.')
        return avatar

class OrganizationEmailSettingsForm(forms.ModelForm):
    password=forms.CharField(label='SMTP-wachtwoord',required=False,widget=forms.PasswordInput(attrs={'autocomplete':'new-password','placeholder':'Ongewijzigd laten'}),help_text='Laat leeg om het opgeslagen wachtwoord te behouden.')
    class Meta:
        model=OrganizationEmailSettings; fields=('host','port','username','password','from_email','use_tls','use_ssl','is_active')
        labels={'host':'SMTP-server','port':'Poort','username':'Gebruikersnaam','from_email':'Afzenderadres','use_tls':'TLS gebruiken','use_ssl':'SSL gebruiken','is_active':'E-mailverzending actief'}
    def clean(self):
        data=super().clean()
        if data.get('use_tls') and data.get('use_ssl'): raise forms.ValidationError('TLS en SSL kunnen niet tegelijk actief zijn.')
        if not self.instance.password_encrypted and not data.get('password'): self.add_error('password','Vul het SMTP-wachtwoord in.')
        return data
    def save(self,commit=True):
        obj=super().save(False); password=self.cleaned_data.get('password')
        if password: obj.set_password(password)
        if commit: obj.save()
        return obj

class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model=Organization; fields=('name','logo','address','postal_code','city','kvk_number','vat_id','iban','payment_term_days','primary_color','quote_prefix','invoice_prefix','quote_valid_days','default_quote_terms','default_invoice_notes')
        widgets={'primary_color':forms.TextInput(attrs={'type':'color'}),'default_quote_terms':forms.Textarea(attrs={'rows':4}),'default_invoice_notes':forms.Textarea(attrs={'rows':4})}
        labels={'name':'Bedrijfsnaam','logo':'Bedrijfslogo','kvk_number':'KvK-nummer','vat_id':'Btw-identificatienummer','payment_term_days':'Standaard betalingstermijn','primary_color':'Huisstijlkleur','quote_prefix':'Offertevoorvoegsel','invoice_prefix':'Factuurvoorvoegsel','quote_valid_days':'Standaard geldigheid offerte','default_quote_terms':'Standaard offertevoorwaarden','default_invoice_notes':'Standaard factuurtekst'}
    def clean_primary_color(self):
        value=self.cleaned_data['primary_color'].lower()
        if len(value)!=7 or value[0]!='#' or any(c not in '0123456789abcdef' for c in value[1:]): raise forms.ValidationError('Kies een geldige hexkleur.')
        return value
    def clean_logo(self):
        logo=self.cleaned_data.get('logo')
        if logo and getattr(logo,'size',0)>5*1024*1024: raise forms.ValidationError('Het logo is groter dan 5 MB.')
        return logo

class TeamMemberForm(UserCreationForm):
    role=forms.ChoiceField(label='Rol',choices=Membership.Role.choices)
    class Meta:
        model=User; fields=('display_name','email','role','password1','password2')
        labels={'display_name':'Volledige naam','email':'E-mailadres'}
    def clean_email(self): return self.cleaned_data['email'].strip().lower()

class TeamMemberEditForm(forms.ModelForm):
    role=forms.ChoiceField(label='Rol',choices=Membership.Role.choices)
    class Meta:
        model=User; fields=('display_name','email','role')
        labels={'display_name':'Volledige naam','email':'E-mailadres'}
    def __init__(self,*args,membership=None,**kwargs):
        super().__init__(*args,**kwargs); self.membership=membership
        if membership: self.fields['role'].initial=membership.role
    def clean_email(self): return self.cleaned_data['email'].strip().lower()

class CustomerForm(forms.ModelForm):
    labels_text=forms.CharField(label='Labels',required=False,help_text='Scheid labels met komma’s, bijvoorbeeld: belangrijk, onderhoud.')
    class Meta:
        model=Customer
        fields=('kind','legal_name','trade_name','email','phone','kvk_number','vat_id','status','owner','address','postal_code','city','billing_address','billing_postal_code','billing_city','payment_term_days','notes')
        widgets={'notes':forms.Textarea(attrs={'rows':4})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization
        self.fields['owner'].queryset=organization.memberships.filter(is_active=True).select_related('user') if organization else Membership.objects.none()
        self.fields['owner'].label_from_instance=lambda x:x.user.display_name
        if self.instance.pk: self.fields['labels_text'].initial=', '.join(self.instance.labels or [])
    def clean_kvk_number(self):
        value=''.join(filter(str.isdigit,self.cleaned_data.get('kvk_number','')))
        if value and len(value)!=8: raise forms.ValidationError('Een KvK-nummer bestaat uit 8 cijfers.')
        qs=Customer.objects.filter(organization=self.organization,kvk_number=value).exclude(pk=self.instance.pk)
        if value and qs.exists(): raise forms.ValidationError('Dit KvK-nummer bestaat al binnen de organisatie.')
        return value
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        obj.labels=[x.strip() for x in self.cleaned_data.get('labels_text','').split(',') if x.strip()][:20]
        if commit: obj.save(); self.save_m2m()
        return obj

class ContactForm(forms.ModelForm):
    class Meta: model=Contact; fields=('first_name','last_name','job_title','email','phone','is_primary')

class CustomerNoteForm(forms.Form):
    kind=forms.ChoiceField(label='Type',choices=[('note','Notitie'),('call','Telefoongesprek'),('email','E-mail')])
    body=forms.CharField(label='Beschrijving',widget=forms.Textarea(attrs={'rows':3,'placeholder':'Leg de afspraak of actie kort vast…'}),max_length=4000)

class CsvImportForm(forms.Form):
    file=forms.FileField(label='CSV-bestand',help_text='UTF-8 CSV, maximaal 5 MB.')
    def clean_file(self):
        f=self.cleaned_data['file']
        if f.size>5*1024*1024: raise forms.ValidationError('Het bestand is groter dan 5 MB.')
        if not f.name.lower().endswith('.csv'): raise forms.ValidationError('Kies een CSV-bestand.')
        return f

class ProductForm(forms.ModelForm):
    class Meta: model=Product; fields=('code','name','description','kind','unit','unit_price','purchase_price','vat_rate','track_stock','stock_quantity','minimum_stock','is_active'); widgets={'description':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,organization=None,**kwargs): super().__init__(*args,**kwargs); self.organization=organization
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save()
        return obj

class QuoteForm(forms.ModelForm):
    class Meta:
        model=Quote; fields=('customer','title','issue_date','valid_until','introduction','terms','internal_notes')
        widgets={'issue_date':forms.DateInput(attrs={'type':'date'}),'valid_until':forms.DateInput(attrs={'type':'date'}),'introduction':forms.Textarea(attrs={'rows':3}),'terms':forms.Textarea(attrs={'rows':4}),'internal_notes':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization
        self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none()
    def clean(self):
        data=super().clean()
        if data.get('valid_until') and data.get('issue_date') and data['valid_until']<data['issue_date']: self.add_error('valid_until','De geldigheidsdatum kan niet vóór de offertedatum liggen.')
        return data
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save()
        return obj

class QuoteLineForm(forms.ModelForm):
    class Meta: model=QuoteLine; fields=('product','description','quantity','unit','unit_price','discount_percent','vat_rate'); widgets={'description':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['product'].queryset=organization.products.filter(is_active=True) if organization else Product.objects.none(); self.fields['description'].required=False
    def clean(self):
        data=super().clean(); product=data.get('product')
        if product:
            data['description']=data.get('description') or product.description or product.name
            if not self.is_bound: return data
        if not data.get('description'): self.add_error('description','Kies een product of vul een omschrijving in.')
        if data.get('quantity',0)<=0: self.add_error('quantity','Het aantal moet groter zijn dan nul.')
        if data.get('discount_percent',0)<0 or data.get('discount_percent',0)>100: self.add_error('discount_percent','Korting moet tussen 0 en 100% liggen.')
        if data.get('vat_rate') not in (0,9,21): self.add_error('vat_rate','Gebruik voor Nederlandse offertes 0%, 9% of 21% btw.')
        return data

class RejectionForm(forms.Form):
    reason=forms.CharField(label='Reden voor afwijzing',widget=forms.Textarea(attrs={'rows':4}),min_length=3,max_length=2000)

class InvoiceForm(forms.ModelForm):
    class Meta:
        model=Invoice; fields=('customer','title','issue_date','delivery_date','due_date','notes')
        widgets={'issue_date':forms.DateInput(attrs={'type':'date'}),'delivery_date':forms.DateInput(attrs={'type':'date'}),'due_date':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':4})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none()
    def clean(self):
        data=super().clean()
        if data.get('due_date') and data.get('issue_date') and data['due_date']<data['issue_date']: self.add_error('due_date','De vervaldatum kan niet vóór de factuurdatum liggen.')
        return data
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save()
        return obj

class InvoiceLineForm(forms.ModelForm):
    class Meta: model=InvoiceLine; fields=('description','quantity','unit','unit_price','discount_percent','vat_rate'); widgets={'description':forms.Textarea(attrs={'rows':2})}
    def clean(self):
        data=super().clean()
        if data.get('quantity',0)<=0: self.add_error('quantity','Het aantal moet groter zijn dan nul.')
        if data.get('discount_percent',0)<0 or data.get('discount_percent',0)>100: self.add_error('discount_percent','Korting moet tussen 0 en 100% liggen.')
        if data.get('vat_rate') not in (0,9,21): self.add_error('vat_rate','Gebruik 0%, 9% of 21% btw.')
        return data

class PaymentForm(forms.ModelForm):
    class Meta: model=Payment; fields=('amount','paid_on','reference'); widgets={'paid_on':forms.DateInput(attrs={'type':'date'})}
    def __init__(self,*args,invoice=None,**kwargs): super().__init__(*args,**kwargs); self.invoice=invoice
    def clean_amount(self):
        amount=self.cleaned_data['amount']
        if amount<=0: raise forms.ValidationError('Het bedrag moet groter zijn dan nul.')
        if self.invoice and amount>self.invoice.outstanding: raise forms.ValidationError('Het bedrag is hoger dan het openstaande bedrag.')
        return amount

class AppointmentForm(forms.ModelForm):
    class Meta:
        model=Appointment; fields=('title','appointment_type','customer','participants','start','end','all_day','location','description','reminder_minutes','recurrence','recurrence_until')
        widgets={'start':forms.DateTimeInput(attrs={'type':'datetime-local'}),'end':forms.DateTimeInput(attrs={'type':'datetime-local'}),'recurrence_until':forms.DateInput(attrs={'type':'date'}),'description':forms.Textarea(attrs={'rows':4}),'participants':forms.CheckboxSelectMultiple()}
        labels={'reminder_minutes':'Herinnering vooraf (minuten)','recurrence_until':'Herhalen tot en met'}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none(); self.fields['participants'].queryset=organization.memberships.filter(is_active=True).select_related('user') if organization else Membership.objects.none(); self.fields['appointment_type'].queryset=organization.appointment_types.filter(is_active=True) if organization else AppointmentType.objects.none(); self.fields['participants'].label_from_instance=lambda x:x.user.display_name
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and data['end']<=data['start']: self.add_error('end','Eindtijd moet na de begintijd liggen.')
        if data.get('recurrence')!='none' and not data.get('recurrence_until'): self.add_error('recurrence_until','Kies een einddatum voor herhaling.')
        if data.get('recurrence_until') and data.get('start') and data['recurrence_until']<data['start'].date(): self.add_error('recurrence_until','De herhaling kan niet vóór de afspraak eindigen.')
        return data

class BoardForm(forms.ModelForm):
    class Meta: model=Board; fields=('name','is_default')
    def __init__(self,*args,organization=None,**kwargs): super().__init__(*args,**kwargs); self.organization=organization
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save()
        return obj

class BoardColumnForm(forms.ModelForm):
    class Meta: model=BoardColumn; fields=('name','color','is_done')

class TaskForm(forms.ModelForm):
    labels_text=forms.CharField(label='Labels',required=False,help_text='Scheid labels met komma’s.')
    class Meta:
        model=Task; fields=('title','description','priority','due_date','assignees','customer','quote','invoice','appointment')
        widgets={'description':forms.Textarea(attrs={'rows':5}),'due_date':forms.DateTimeInput(attrs={'type':'datetime-local'}),'assignees':forms.CheckboxSelectMultiple()}
        labels={'due_date':'Deadline','assignees':'Toegewezen aan','appointment':'Agenda-afspraak'}
    def __init__(self,*args,organization=None,board=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.board=board
        self.fields['assignees'].queryset=organization.memberships.filter(is_active=True).select_related('user') if organization else Membership.objects.none()
        self.fields['assignees'].label_from_instance=lambda x:x.user.display_name
        self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none()
        self.fields['quote'].queryset=organization.quotes.filter(is_archived=False) if organization else Quote.objects.none()
        self.fields['invoice'].queryset=organization.invoices.filter(is_archived=False) if organization else Invoice.objects.none()
        self.fields['appointment'].queryset=organization.appointments.filter(is_cancelled=False) if organization else Appointment.objects.none()
        if self.instance.pk: self.fields['labels_text'].initial=', '.join(self.instance.labels or [])
    def save(self,commit=True):
        obj=super().save(False); obj.board=self.board; obj.organization=self.organization
        obj.labels=[x.strip() for x in self.cleaned_data.get('labels_text','').split(',') if x.strip()][:20]
        if commit: obj.save(); self.save_m2m()
        return obj

class TaskCommentForm(forms.Form):
    body=forms.CharField(label='Opmerking',max_length=4000,widget=forms.Textarea(attrs={'rows':3,'placeholder':'Schrijf een opmerking…'}))

class ChecklistItemForm(forms.Form):
    text=forms.CharField(label='Checklistitem',max_length=240)

class BackupConfigurationForm(forms.ModelForm):
    weekday=forms.ChoiceField(label='Dag van de week',choices=((0,'Maandag'),(1,'Dinsdag'),(2,'Woensdag'),(3,'Donderdag'),(4,'Vrijdag'),(5,'Zaterdag'),(6,'Zondag')))
    class Meta:
        model=BackupConfiguration; fields=('max_backups','automatic_enabled','frequency','weekday','run_at')
        widgets={'run_at':forms.TimeInput(attrs={'type':'time'})}
        labels={'max_backups':'Maximaal aantal back-ups','automatic_enabled':'Automatische back-ups inschakelen','frequency':'Frequentie','run_at':'Tijdstip'}
    def clean_max_backups(self):
        value=self.cleaned_data['max_backups']
        if not 1<=value<=365: raise forms.ValidationError('Kies een aantal tussen 1 en 365.')
        return value

class TaskAttachmentForm(forms.ModelForm):
    class Meta: model=TaskAttachment; fields=('file',)
    def clean_file(self):
        uploaded=self.cleaned_data['file']; extension=uploaded.name.rsplit('.',1)[-1].lower() if '.' in uploaded.name else ''
        if uploaded.size>10*1024*1024: raise forms.ValidationError('Het bestand is groter dan 10 MB.')
        if extension in {'exe','com','bat','cmd','sh','ps1','php','js','jar','msi','scr'}: raise forms.ValidationError('Dit bestandstype is niet toegestaan.')
        return uploaded

class OpportunityForm(forms.ModelForm):
    class Meta: model=Opportunity; fields=('customer','title','stage','expected_revenue','probability','follow_up_date','owner','notes'); widgets={'follow_up_date':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':4})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none(); self.fields['owner'].queryset=organization.memberships.filter(is_active=True,is_removed=False) if organization else Membership.objects.none()
    def clean_probability(self):
        value=self.cleaned_data['probability']
        if value>100: raise forms.ValidationError('Waarschijnlijkheid mag maximaal 100% zijn.')
        return value
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save()
        return obj

class ProjectForm(forms.ModelForm):
    class Meta: model=Project; fields=('customer','name','status','budget','start_date','end_date','members','notes'); widgets={'start_date':forms.DateInput(attrs={'type':'date'}),'end_date':forms.DateInput(attrs={'type':'date'}),'members':forms.CheckboxSelectMultiple(),'notes':forms.Textarea(attrs={'rows':4})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none(); self.fields['members'].queryset=organization.memberships.filter(is_active=True,is_removed=False) if organization else Membership.objects.none()
    def clean(self):
        data=super().clean()
        if data.get('start_date') and data.get('end_date') and data['end_date']<data['start_date']: self.add_error('end_date','Einddatum ligt vóór de startdatum.')
        return data
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save(); self.save_m2m()
        return obj

class TimeEntryForm(forms.ModelForm):
    class Meta: model=TimeEntry; fields=('date','hours','hourly_rate','description'); widgets={'date':forms.DateInput(attrs={'type':'date'})}
    def clean_hours(self):
        value=self.cleaned_data['hours']
        if value<=0 or value>24: raise forms.ValidationError('Uren moeten tussen 0 en 24 liggen.')
        return value

class GlobalTimeEntryForm(TimeEntryForm):
    class Meta: model=TimeEntry; fields=('project','date','hours','hourly_rate','description'); widgets={'date':forms.DateInput(attrs={'type':'date'})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['project'].queryset=organization.projects.exclude(status=Project.Status.CANCELLED).select_related('customer') if organization else Project.objects.none()
        self.fields['project'].label_from_instance=lambda project:f'{project.name} · {project.customer}'

class MileageEntryForm(forms.ModelForm):
    class Meta: model=MileageEntry; fields=('date','kilometers','rate','description'); widgets={'date':forms.DateInput(attrs={'type':'date'})}

class ExpenseForm(forms.ModelForm):
    class Meta: model=Expense; fields=('date','amount','description','receipt'); widgets={'date':forms.DateInput(attrs={'type':'date'})}
    def clean_receipt(self):
        value=self.cleaned_data.get('receipt')
        if value and value.size>10*1024*1024: raise forms.ValidationError('Het bewijsstuk is groter dan 10 MB.')
        return value

class ProjectDocumentForm(forms.ModelForm):
    class Meta: model=ProjectDocument; fields=('title','file','visible_to_portal'); labels={'visible_to_portal':'Zichtbaar in klantportaal'}
    def clean_file(self):
        value=self.cleaned_data['file']
        if value.size>20*1024*1024: raise forms.ValidationError('Het document is groter dan 20 MB.')
        return value

class RecurringInvoiceScheduleForm(forms.ModelForm):
    line_description=forms.CharField(label='Factuurregel',max_length=300)
    line_quantity=forms.DecimalField(label='Aantal',min_value=Decimal('0.01'),initial=1,max_digits=10,decimal_places=2)
    line_unit=forms.CharField(label='Eenheid',initial='stuk',max_length=30)
    line_price=forms.DecimalField(label='Prijs exclusief btw',min_value=0,max_digits=12,decimal_places=2)
    line_vat=forms.ChoiceField(label='Btw',choices=((0,'0%'),(9,'9%'),(21,'21%')),initial=21)
    class Meta: model=RecurringInvoiceSchedule; fields=('customer','title','frequency','next_run','payment_term_days','notes','is_active'); widgets={'next_run':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization; self.fields['customer'].queryset=organization.customers.exclude(status=Customer.Status.ARCHIVED) if organization else Customer.objects.none()
        if self.instance.pk and self.instance.lines:
            line=self.instance.lines[0]
            for field,key in (('line_description','description'),('line_quantity','quantity'),('line_unit','unit'),('line_price','unit_price'),('line_vat','vat_rate')): self.fields[field].initial=line.get(key)
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization; obj.lines=[{'description':self.cleaned_data['line_description'],'quantity':str(self.cleaned_data['line_quantity']),'unit':self.cleaned_data['line_unit'],'unit_price':str(self.cleaned_data['line_price']),'vat_rate':int(self.cleaned_data['line_vat'])}]
        if commit: obj.save()
        return obj

class ReminderPolicyForm(forms.ModelForm):
    class Meta: model=ReminderPolicy; fields=('enabled','first_after_days','second_after_days','final_after_days'); labels={'enabled':'Automatisch herinneringen klaarzetten','first_after_days':'Eerste herinnering na dagen','second_after_days':'Tweede herinnering na dagen','final_after_days':'Laatste herinnering na dagen'}
    def clean(self):
        data=super().clean(); values=[data.get('first_after_days'),data.get('second_after_days'),data.get('final_after_days')]
        if all(v is not None for v in values) and values!=sorted(values): raise forms.ValidationError('De herinneringstermijnen moeten oplopend zijn.')
        return data

class EmailTemplateForm(forms.ModelForm):
    class Meta: model=EmailTemplate; fields=('subject','body'); widgets={'body':forms.Textarea(attrs={'rows':10})}; labels={'subject':'Onderwerp','body':'Bericht'}

class TenantModelForm(forms.ModelForm):
    def __init__(self,*args,organization=None,**kwargs): super().__init__(*args,**kwargs); self.organization=organization
    def save(self,commit=True):
        obj=super().save(False); obj.organization=self.organization
        if commit: obj.save(); self.save_m2m()
        return obj

class CommunicationForm(TenantModelForm):
    class Meta: model=Communication; fields=('customer','contact','recipient','subject','body'); widgets={'body':forms.Textarea(attrs={'rows':8})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,organization=organization,**kwargs); self.fields['customer'].queryset=organization.customers.all(); self.fields['contact'].queryset=organization.contacts.filter(is_active=True)

class ContractForm(TenantModelForm):
    class Meta: model=Contract; fields=('customer','title','status','start_date','end_date','notice_days','auto_renew','value','owner','terms'); widgets={'start_date':forms.DateInput(attrs={'type':'date'}),'end_date':forms.DateInput(attrs={'type':'date'}),'terms':forms.Textarea(attrs={'rows':6})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,organization=organization,**kwargs); self.fields['customer'].queryset=organization.customers.all(); self.fields['owner'].queryset=organization.memberships.filter(is_active=True,is_removed=False)
    def clean(self):
        data=super().clean()
        if data.get('end_date') and data.get('start_date') and data['end_date']<data['start_date']: self.add_error('end_date','Einddatum ligt vóór de startdatum.')
        return data

class ServiceTicketForm(TenantModelForm):
    class Meta: model=ServiceTicket; fields=('customer','subject','description','status','priority','assignee','due_at'); widgets={'description':forms.Textarea(attrs={'rows':6}),'due_at':forms.DateTimeInput(attrs={'type':'datetime-local'})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,organization=organization,**kwargs); self.fields['customer'].queryset=organization.customers.all(); self.fields['assignee'].queryset=organization.memberships.filter(is_active=True,is_removed=False)

class WorkOrderForm(TenantModelForm):
    class Meta: model=WorkOrder; fields=('customer','ticket','assigned_to','title','address','scheduled_start','scheduled_end','route_position','status','report','photo','customer_signature'); widgets={'scheduled_start':forms.DateTimeInput(attrs={'type':'datetime-local'}),'scheduled_end':forms.DateTimeInput(attrs={'type':'datetime-local'}),'report':forms.Textarea(attrs={'rows':5}),'photo':forms.ClearableFileInput(attrs={'accept':'image/*','capture':'environment'}),'customer_signature':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,organization=organization,**kwargs); self.fields['customer'].queryset=organization.customers.all(); self.fields['ticket'].queryset=organization.service_tickets.all(); self.fields['assigned_to'].queryset=organization.memberships.filter(is_active=True,is_removed=False)
    def clean(self):
        data=super().clean()
        if data.get('scheduled_start') and data.get('scheduled_end') and data['scheduled_end']<=data['scheduled_start']: self.add_error('scheduled_end','Eindtijd moet na de starttijd liggen.')
        photo=data.get('photo')
        if photo and getattr(photo,'size',0)>10*1024*1024: self.add_error('photo','De foto is groter dan 10 MB.')
        return data

class StockMovementForm(TenantModelForm):
    class Meta: model=StockMovement; fields=('product','kind','quantity','reason')
    def __init__(self,*args,organization=None,**kwargs): super().__init__(*args,organization=organization,**kwargs); self.fields['product'].queryset=organization.products.filter(track_stock=True,is_active=True)

class DocumentTemplateForm(TenantModelForm):
    layout_order=forms.CharField(widget=forms.HiddenInput(),required=False)
    class Meta: model=DocumentTemplate; fields=('kind','name','header','footer','primary_color','is_default'); widgets={'header':forms.Textarea(attrs={'rows':4}),'footer':forms.Textarea(attrs={'rows':4}),'primary_color':forms.TextInput(attrs={'type':'color'})}
    def save(self,commit=True):
        obj=super().save(False); obj.layout=[x for x in self.cleaned_data.get('layout_order','').split(',') if x in ('header','recipient','lines','totals','terms','footer')]
        if commit:
            if obj.is_default: DocumentTemplate.objects.filter(organization=self.organization,kind=obj.kind,is_default=True).exclude(pk=obj.pk).update(is_default=False)
            obj.save()
        return obj

class CalendarConnectionForm(TenantModelForm):
    secret=forms.CharField(required=False,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    class Meta: model=CalendarConnection; fields=('membership','provider','endpoint','account','calendar_id','enabled')
    def __init__(self,*args,organization=None,**kwargs): super().__init__(*args,organization=organization,**kwargs); self.fields['membership'].queryset=organization.memberships.filter(is_active=True,is_removed=False)
    def save(self,commit=True):
        obj=super().save(False); from .encryption import encrypt_secret
        if self.cleaned_data.get('secret'): obj.secret_encrypted=encrypt_secret(self.cleaned_data['secret'])
        if commit: obj.save()
        return obj

class IntegrationEndpointForm(TenantModelForm):
    secret=forms.CharField(required=False,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    events_text=forms.CharField(required=False,help_text='Komma-gescheiden gebeurtenissen')
    class Meta: model=IntegrationEndpoint; fields=('kind','name','endpoint','enabled')
    def save(self,commit=True):
        obj=super().save(False); obj.events=[x.strip() for x in self.cleaned_data.get('events_text','').split(',') if x.strip()]
        if self.cleaned_data.get('secret'): obj.set_secret(self.cleaned_data['secret'])
        if commit: obj.save()
        return obj

class BankImportForm(forms.Form):
    file=forms.FileField(label='CAMT/MT940/CSV-bankbestand')
    def clean_file(self):
        value=self.cleaned_data['file']
        if value.size>10*1024*1024: raise forms.ValidationError('Bestand is groter dan 10 MB.')
        return value

class DataImportForm(BankImportForm):
    entity=forms.ChoiceField(label='Gegevenstype',choices=(('customers','Klanten'),('products','Producten'),('contracts','Contracten')))
    dry_run=forms.BooleanField(label='Alleen controleren',required=False,initial=True)
