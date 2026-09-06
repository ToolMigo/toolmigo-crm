from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Appointment, AppointmentType, AuditEvent, Board, BoardColumn, Contact, Customer, CustomerActivity, DocumentSequence, EmailDelivery, Invoice, InvoiceLine, Membership, Organization, OrganizationEmailSettings, Payment, Product, Quote, QuoteLine, Task, TaskAttachment, TaskChecklistItem, TaskComment, User
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering=('email',); list_display=('email','display_name','is_active','is_platform_admin')
    fieldsets=((None,{'fields':('email','password')}),('Persoonlijk',{'fields':('display_name',)}),('Rechten',{'fields':('is_active','is_staff','is_superuser','is_platform_admin','groups','user_permissions')}),('Datums',{'fields':('last_login','date_joined')}))
    add_fieldsets=((None,{'classes':('wide',),'fields':('email','display_name','password1','password2')}),)
admin.site.register(Organization); admin.site.register(Membership)
admin.site.register(Customer); admin.site.register(Contact); admin.site.register(CustomerActivity)
admin.site.register(Product); admin.site.register(Quote); admin.site.register(QuoteLine); admin.site.register(DocumentSequence)
admin.site.register(Invoice); admin.site.register(InvoiceLine); admin.site.register(Payment); admin.site.register(EmailDelivery)
admin.site.register(AppointmentType); admin.site.register(Appointment)
admin.site.register(OrganizationEmailSettings)
admin.site.register(Board); admin.site.register(BoardColumn); admin.site.register(Task); admin.site.register(TaskChecklistItem); admin.site.register(TaskComment); admin.site.register(TaskAttachment)
@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display=('created_at','organization','actor','action'); readonly_fields=[f.name for f in AuditEvent._meta.fields]
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
