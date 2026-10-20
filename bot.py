import os
import secrets
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE)
BOT_TOKEN = os.getenv('BOT_TOKEN','').strip()
SUPABASE_URL = os.getenv('SUPABASE_URL','').strip().rstrip('/')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY','').strip()
ADMIN_TELEGRAM_ID = os.getenv('ADMIN_TELEGRAM_ID','').strip()
WEBHOOK_URL = os.getenv('WEBHOOK_URL','').strip().rstrip('/')
MINI_APP_URL = os.getenv('MINI_APP_URL', WEBHOOK_URL).strip().rstrip('/')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME','').strip().lstrip('@')
TG = f'https://api.telegram.org/bot{BOT_TOKEN}'


def tg(method, payload):
    if not BOT_TOKEN: return {'ok':False,'description':'BOT_TOKEN missing'}
    try:
        r=requests.post(f'{TG}/{method}', json=payload, timeout=20)
        return r.json()
    except Exception as e: return {'ok':False,'description':str(e)}


def headers(prefer='return=representation'):
    return {'apikey':SUPABASE_SERVICE_KEY,'Authorization':f'Bearer {SUPABASE_SERVICE_KEY}',
            'Content-Type':'application/json','Prefer':prefer}


def db_get(table, params=None):
    r=requests.get(f'{SUPABASE_URL}/rest/v1/{table}',headers=headers(),params=params or {},timeout=20)
    return r


def db_post(table, data, params=None):
    return requests.post(f'{SUPABASE_URL}/rest/v1/{table}',headers=headers(),params=params or {},json=data,timeout=20)


def db_patch(table, data, params):
    return requests.patch(f'{SUPABASE_URL}/rest/v1/{table}',headers=headers(),params=params,json=data,timeout=20)


def db_delete(table, params):
    return requests.delete(f'{SUPABASE_URL}/rest/v1/{table}',headers=headers(),params=params,timeout=20)


def user_id(payload):
    payload = payload or {}
    u = payload.get('user')
    if isinstance(u, dict):
        return str(u.get('id') or payload.get('telegram_id') or '').strip()
    return str(u or payload.get('telegram_id') or '').strip()


def require_user(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not user_id(request.get_json(silent=True) or request.args):
            return jsonify(ok=False,error='Telegram foydalanuvchisi topilmadi'),400
        return fn(*args,**kwargs)
    return wrapped


def is_admin(value): return ADMIN_TELEGRAM_ID and str(value).strip()==ADMIN_TELEGRAM_ID

@app.get('/')
def home(): return send_from_directory(BASE,'index.html')
@app.get('/admin')
def admin_page(): return send_from_directory(BASE,'admin.html')
@app.get('/health')
def health(): return jsonify(ok=True,service='Malina',time=datetime.now(timezone.utc).isoformat())

@app.get('/api/config')
def config(): return jsonify(ok=True,admin_username=ADMIN_USERNAME,mini_app_url=MINI_APP_URL)

@app.get('/api/profile')
@require_user
def get_profile():
    uid=user_id(request.args); r=db_get('profiles',{'telegram_id':f'eq.{uid}','select':'*','limit':'1'})
    if r.status_code>=300: return jsonify(ok=False,error=r.text),500
    return jsonify(ok=True,profile=(r.json() or [None])[0])

@app.post('/api/profile')
@require_user
def save_profile():
    p=request.get_json() or {}; uid=user_id(p)
    profile={'telegram_id':uid,'name':str(p.get('name','')).strip(),'age':int(p.get('age') or 0),
             'gender':p.get('gender',''),'city':p.get('city',''),'bio':p.get('bio',''),
             'interests':p.get('interests',[]),'photos':p.get('photos',[]),'is_blocked':False,
             'last_active':datetime.now(timezone.utc).isoformat()}
    if not profile['name'] or not profile['age'] or not profile['gender'] or not profile['photos']:
        return jsonify(ok=False,error='Ism, yosh, jins va kamida bitta rasm kerak'),400
    r=db_post('profiles',profile,{'on_conflict':'telegram_id'})
    if r.status_code>=300: return jsonify(ok=False,error=r.text),500
    start_param=str(p.get('start_param',''))
    if start_param.startswith('ref_'):
        inviter=start_param[4:]
        if inviter and inviter != uid:
            db_post('referrals',{'inviter_id':inviter,'invited_id':uid,'status':'confirmed'}, {'on_conflict':'invited_id'})
    return jsonify(ok=True,profile=(r.json() or [profile])[0])

@app.get('/api/profiles')
@require_user
def profiles():
    uid=user_id(request.args); city=request.args.get('city','')
    params={'select':'telegram_id,name,age,gender,city,bio,interests,photos,is_premium','is_blocked':'eq.false','telegram_id':f'neq.{uid}','limit':'50','order':'last_active.desc'}
    if city: params['city']=f'eq.{city}'
    r=db_get('profiles',params)
    if r.status_code>=300: return jsonify(ok=False,error=r.text),500
    return jsonify(ok=True,profiles=r.json())

@app.post('/api/action')
@require_user
def action():
    p=request.get_json() or {}; uid=user_id(p); target=str(p.get('target_id','')); act=p.get('action','pass')
    if not target or target==uid: return jsonify(ok=False,error='Profil noto‘g‘ri'),400
    if act not in ('like','pass','message'): return jsonify(ok=False,error='Action noto‘g‘ri'),400
    if act=='like':
        r=db_post('likes',{'from_id':uid,'to_id':target,'kind':'like'},{'on_conflict':'from_id,to_id'})
        if r.status_code>=300 and r.status_code!=409: return jsonify(ok=False,error=r.text),500
        back=db_get('likes',{'from_id':f'eq.{target}','to_id':f'eq.{uid}','select':'id','limit':'1'})
        match=back.status_code<300 and bool(back.json())
        return jsonify(ok=True,match=match)
    if act=='message':
        text=str(p.get('text','')).strip()
        if not text: return jsonify(ok=False,error='Xabar bo‘sh'),400
        r=db_post('messages',{'from_id':uid,'to_id':target,'text':text})
        return jsonify(ok=r.status_code<300)
    return jsonify(ok=True)

@app.get('/api/likes')
@require_user
def likes():
    uid=user_id(request.args); r=db_get('likes',{'from_id':f'eq.{uid}','select':'to_id,created_at','order':'created_at.desc'})
    if r.status_code>=300:return jsonify(ok=False,error=r.text),500
    ids=[x['to_id'] for x in r.json()]; result=[]
    if ids:
        q=db_get('profiles',{'telegram_id':f'in.({",".join(ids)})','select':'*'}); result=q.json() if q.status_code<300 else []
    return jsonify(ok=True,profiles=result)

@app.get('/api/messages')
@require_user
def messages():
    uid=user_id(request.args); r=db_get('messages',{'or':f'(from_id.eq.{uid},to_id.eq.{uid})','select':'*','order':'created_at.desc','limit':'100'})
    return jsonify(ok=r.status_code<300,messages=r.json() if r.status_code<300 else [])

@app.get('/api/referral')
@require_user
def referral():
    uid=user_id(request.args); r=db_get('referrals',{'inviter_id':f'eq.{uid}','select':'*','order':'created_at.desc'})
    rows=r.json() if r.status_code<300 else []
    confirmed=sum(1 for x in rows if x.get('status')=='confirmed')
    next_goal=10 if confirmed<10 else 20 if confirmed<20 else 30 if confirmed<30 else 999
    return jsonify(ok=True,referral={'link':f'https://t.me/club_Malina_bot?start=ref_{uid}','invited':len(rows),'confirmed':confirmed,'remaining':max(0,next_goal-confirmed),'goal':next_goal,'bonuses':[{'count':10,'reward':'4 kun Premium'},{'count':20,'reward':'1 hafta Premium'},{'count':30,'reward':'1 oy Premium'}]})

@app.post('/api/report')
@require_user
def report():
    p=request.get_json() or {}; r=db_post('reports',{'reporter_id':user_id(p),'reported_id':str(p.get('reported_id','')),'reason':p.get('reason',''),'details':p.get('details','')})
    return jsonify(ok=r.status_code<300)

@app.delete('/api/profile')
@require_user
def delete_profile():
    uid=user_id(request.get_json(silent=True) or request.args)
    r=db_delete('profiles',{'telegram_id':f'eq.{uid}'})
    return jsonify(ok=r.status_code<300)

@app.get('/api/admin/stats')
def admin_stats():
    if not is_admin(request.args.get('admin_id','')): return jsonify(ok=False,error='Admin ruxsati yo‘q'),403
    users=db_get('profiles',{'select':'telegram_id,name,age,gender,city,is_premium,is_blocked,last_active','limit':'5000'}); rows=users.json() if users.status_code<300 else []
    reps=db_get('reports',{'select':'id,status','status':'eq.open'}); open_reports=len(reps.json()) if reps.status_code<300 else 0
    return jsonify(ok=True,stats={'total':len(rows),'active':len(rows),'premium':sum(1 for x in rows if x.get('is_premium')),'blocked':sum(1 for x in rows if x.get('is_blocked')),'open_reports':open_reports},users=rows)

@app.post('/api/admin/block')
def admin_block():
    p=request.get_json() or {}
    if not is_admin(p.get('admin_id')): return jsonify(ok=False,error='Ruxsat yo‘q'),403
    r=db_patch('profiles',{'is_blocked':bool(p.get('blocked',True))},{'telegram_id':f'eq.{p.get("target_id","")}'}); return jsonify(ok=r.status_code<300)

@app.post('/api/admin/broadcast')
def admin_broadcast():
    p=request.get_json() or {}
    if not is_admin(p.get('admin_id')): return jsonify(ok=False,error='Ruxsat yo‘q'),403
    text=str(p.get('text','')).strip(); rows=db_get('profiles',{'select':'telegram_id','is_blocked':'eq.false','limit':'5000'}).json()
    sent=failed=0
    for row in rows:
        result=tg('sendMessage',{'chat_id':row['telegram_id'],'text':text})
        sent+=bool(result.get('ok')); failed+=not result.get('ok')
    db_post('broadcast_logs',{'message':text,'sent_count':sent,'failed_count':failed})
    return jsonify(ok=True,sent=sent,failed=failed)

@app.post('/webhook')
def webhook():
    update=request.get_json(silent=True) or {}; msg=update.get('message') or {}; chat=msg.get('chat') or {}; text=msg.get('text','')
    if text.startswith('/start'):
        tg('sendMessage',{'chat_id':chat.get('id'),'text':'Malina’ga xush kelibsiz! Profilingizni yarating va mos insonlarni toping.','reply_markup':{'inline_keyboard':[[{'text':'Tanishuvni boshlash','web_app':{'url':MINI_APP_URL}}]]}})
    return jsonify(ok=True)

@app.get('/set-webhook')
def set_webhook():
    if not WEBHOOK_URL:return jsonify(ok=False,error='WEBHOOK_URL missing'),400
    return jsonify(tg('setWebhook',{'url':f'{WEBHOOK_URL}/webhook','drop_pending_updates':True}))

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
