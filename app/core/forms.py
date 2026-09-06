from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Appointment, AppointmentType, Board, BoardColumn, Contact, Customer, Invoice, InvoiceLine, Membership, OrganizationEmailSettings, Payment, Product, Quote, QuoteLine, Task, TaskAttachment, User

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
    class Meta: model=Product; fields=('code','name','description','kind','unit','unit_price','vat_rate','is_active'); widgets={'description':forms.Textarea(attrs={'rows':3})}
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

class TaskAttachmentForm(forms.ModelForm):
    class Meta: model=TaskAttachment; fields=('file',)
    def clean_file(self):
        uploaded=self.cleaned_data['file']; extension=uploaded.name.rsplit('.',1)[-1].lower() if '.' in uploaded.name else ''
        if uploaded.size>10*1024*1024: raise forms.ValidationError('Het bestand is groter dan 10 MB.')
        if extension in {'exe','com','bat','cmd','sh','ps1','php','js','jar','msi','scr'}: raise forms.ValidationError('Dit bestandstype is niet toegestaan.')
        return uploaded
