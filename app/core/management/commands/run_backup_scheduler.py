import time
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.backups import create_backup, run_pending_restore
from core.models import BackupConfiguration
from core.automation import generate_recurring_drafts, queue_payment_reminders

class Command(BaseCommand):
    help='Maakt geplande back-ups volgens de instellingen in het CRM.'
    def handle(self,*args,**options):
        self.stdout.write('Back-upplanner gestart.')
        while True:
            if run_pending_restore():
                self.stdout.write('Herstelopdracht verwerkt.'); time.sleep(5); continue
            now=timezone.localtime(); config=BackupConfiguration.load()
            due=config.automatic_enabled and now.time().replace(second=0,microsecond=0)>=config.run_at and config.last_run_date!=now.date()
            due=due and (config.frequency=='daily' or config.weekday==now.weekday())
            if due and cache.add('automatic-backup-lock',str(now.date()),timeout=300):
                try:
                    folder=create_backup(); config.last_run_date=now.date(); config.save(update_fields=['last_run_date','updated_at']); self.stdout.write(f'Back-up {folder.name} aangemaakt.')
                except Exception as exc: self.stderr.write(f'Automatische back-up mislukt: {exc}')
                finally: cache.delete('automatic-backup-lock')
            if now.minute%5==0 and cache.add('financial-automation-lock',now.strftime('%Y%m%d%H%M'),timeout=240):
                try:
                    generated=generate_recurring_drafts(); reminders=queue_payment_reminders()
                    if generated or reminders: self.stdout.write(f'Automatisering: {len(generated)} conceptfacturen, {len(reminders)} herinneringen.')
                except Exception as exc: self.stderr.write(f'Financiële automatisering mislukt: {exc}')
            time.sleep(30)
