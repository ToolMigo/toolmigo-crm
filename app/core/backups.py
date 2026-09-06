import hashlib
import json
import os
import subprocess
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings

ALLOWED_FILES={'database.dump','media.tar.gz','manifest.txt','SHA256SUMS'}

def backup_root():
    root=Path(settings.BACKUP_ROOT).resolve(); root.mkdir(parents=True,exist_ok=True); return root

def create_backup(apply_retention=True):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=backup_root()/stamp; target.mkdir(mode=0o700)
    db=settings.DATABASES['default']; env=os.environ.copy(); env['PGPASSWORD']=db['PASSWORD']
    command=['pg_dump','-h',db['HOST'],'-p',str(db['PORT']),'-U',db['USER'],'-d',db['NAME'],'--format=custom','--no-owner','--no-acl','--file',str(target/'database.dump')]
    try:
        subprocess.run(command,env=env,check=True,capture_output=True,text=True,timeout=300)
        with tarfile.open(target/'media.tar.gz','w:gz') as archive:
            media=Path(settings.MEDIA_ROOT)
            if media.exists(): archive.add(media,arcname='.')
        (target/'manifest.txt').write_text(f'created_utc={stamp}\ndatabase_format=postgresql_custom\nmedia_format=tar_gzip\n',encoding='utf-8')
        lines=[]
        for name in ('database.dump','media.tar.gz','manifest.txt'):
            digest=hashlib.sha256((target/name).read_bytes()).hexdigest(); lines.append(f'{digest}  {name}')
        (target/'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    except Exception:
        for item in target.iterdir(): item.unlink()
        target.rmdir(); raise
    if apply_retention: enforce_retention()
    return target

def enforce_retention(max_backups=None):
    if max_backups is None:
        from .models import BackupConfiguration
        max_backups=BackupConfiguration.load().max_backups
    folders=sorted((p for p in backup_root().glob('20??????T??????Z') if p.is_dir()),reverse=True)
    for folder in folders[max_backups:]: shutil.rmtree(folder)

def list_backups():
    items=[]
    for folder in sorted(backup_root().glob('20??????T??????Z'),reverse=True):
        if not folder.is_dir(): continue
        valid=verify_backup(folder); total=0
        for name in ALLOWED_FILES:
            path=folder/name
            if path.is_file(): total+=path.stat().st_size
        try: created_at=datetime.strptime(folder.name,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        except ValueError: created_at=None
        items.append({'name':folder.name,'created_at':created_at,'size':total,'valid':valid})
    return items

def verify_backup(folder):
    checksum_file=folder/'SHA256SUMS'
    if not checksum_file.is_file(): return False
    try:
        expected={}
        for line in checksum_file.read_text(encoding='utf-8').splitlines():
            digest,name=line.split('  ',1); expected[name]=digest
        for name in ('database.dump','media.tar.gz','manifest.txt'):
            path=folder/name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected.get(name): return False
        return True
    except (OSError,ValueError):
        return False

def backup_file(backup_name,filename):
    if filename not in ALLOWED_FILES or not backup_name.isascii() or len(backup_name)!=16: return None
    path=(backup_root()/backup_name/filename).resolve()
    try: path.relative_to(backup_root())
    except ValueError: return None
    return path if path.is_file() else None

def delete_backup(backup_name):
    folder=backup_file(backup_name,'SHA256SUMS')
    if not folder: return False
    try: shutil.rmtree(folder.parent)
    except FileNotFoundError: return False
    return True

def request_restore(backup_name):
    folder=backup_root()/backup_name
    if not folder.is_dir() or not verify_backup(folder): raise ValueError('Deze back-up is onvolledig of beschadigd.')
    request_file=backup_root()/'.restore-request.json'
    if request_file.exists(): raise ValueError('Er staat al een herstelopdracht in de wachtrij.')
    temporary=backup_root()/'.restore-request.tmp'
    temporary.write_text(json.dumps({'backup':backup_name}),encoding='utf-8'); temporary.replace(request_file)

def restore_status():
    path=backup_root()/'.restore-status.json'
    if not path.exists(): return None
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError): return None

def run_pending_restore():
    request_file=backup_root()/'.restore-request.json'
    if not request_file.exists(): return False
    data=json.loads(request_file.read_text(encoding='utf-8')); request_file.unlink()
    name=data.get('backup',''); folder=backup_root()/name
    status_file=backup_root()/'.restore-status.json'
    def status(state,message):
        temp=backup_root()/'.restore-status.tmp'; temp.write_text(json.dumps({'state':state,'backup':name,'message':message,'updated_at':datetime.now(timezone.utc).isoformat()}),encoding='utf-8'); temp.replace(status_file)
    if not folder.is_dir() or not verify_backup(folder): status('failed','Back-upcontrole mislukt.'); return True
    status('running','Database en bestanden worden teruggezet.')
    db=settings.DATABASES['default']; env=os.environ.copy(); env['PGPASSWORD']=db['PASSWORD']
    common=['-h',db['HOST'],'-p',str(db['PORT']),'-U',db['USER']]
    try:
        safety=create_backup(apply_retention=False)
        status('running',f'Veiligheidsback-up {safety.name} gemaakt; herstel wordt uitgevoerd.')
        from django.db import connections
        connections.close_all()
        subprocess.run(['psql',*common,'-d','postgres','-c',f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db['NAME']}' AND pid <> pg_backend_pid();"],env=env,check=True,capture_output=True,text=True,timeout=60)
        subprocess.run(['dropdb',*common,'--if-exists',db['NAME']],env=env,check=True,capture_output=True,text=True,timeout=60)
        subprocess.run(['createdb',*common,'-O',db['USER'],db['NAME']],env=env,check=True,capture_output=True,text=True,timeout=60)
        subprocess.run(['pg_restore',*common,'-d',db['NAME'],'--no-owner','--no-acl',str(folder/'database.dump')],env=env,check=True,capture_output=True,text=True,timeout=600)
        media=Path(settings.MEDIA_ROOT); media.mkdir(parents=True,exist_ok=True)
        for item in media.iterdir(): shutil.rmtree(item) if item.is_dir() else item.unlink()
        with tarfile.open(folder/'media.tar.gz','r:gz') as archive: archive.extractall(media,filter='data')
        connections.close_all()
        enforce_retention(); status('completed',f'De back-up is succesvol teruggezet. Veiligheidsback-up: {safety.name}.')
    except Exception as exc:
        status('failed',f'Terugzetten mislukt: {str(exc)[:300]}')
    return True
