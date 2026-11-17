"""Integration checks against a disposable SQLite DB; no production/AI calls."""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ['JWT_SECRET_KEY'] = 'test-only-secret-never-used-in-production-12345'
os.environ['JWT_ALGORITHM'] = 'HS256'
os.environ['JWT_EXPIRE_MINUTES'] = '1440'
os.environ.setdefault('APP_AI_BASE_URL', '')
os.environ.setdefault('APP_AI_KEY', '')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from core.database import Base, get_db
from core.auth import create_access_token
from models.users_profiles import Users_profiles
from models.reports import Reports
from models.doctor_patients import Doctor_patients
from models.email_codes import Email_codes
from models.auth_limits import Auth_limits
from routers import analysis, custom_auth, invite, reports
from services.access import hash_password, verify_password, migrate_passwords, session_token, report_token

@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///' + (tmp_path / 'audit.db').as_posix(), poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            for uid, role in [('d1','doctor'),('d2','doctor'),('p1','patient'),('p2','patient')]:
                db.add(Users_profiles(user_id=uid, role=role, full_name=uid, email=uid+'@test.example', phone='old-password' if role=='doctor' else None, email_verified=True))
            db.add(Doctor_patients(user_id='d1', patient_id='p1', status='active'))
            db.add_all([Reports(id=1,user_id='p1',image_data='data:image/png;base64,AA=='), Reports(id=2,user_id='d2'), Reports(id=3,user_id=None)])
            await db.commit()
            await migrate_passwords(db)
    asyncio.run(setup())
    async def override():
        async with sessions() as db:
            yield db
    app = FastAPI()
    app.dependency_overrides[get_db] = override
    for module in (custom_auth, reports, invite, analysis):
        app.include_router(module.router)
    monkeypatch.setattr(custom_auth, 'send_code_email', lambda *a: True)
    with TestClient(app) as c:
        c.sessions = sessions
        yield c
    asyncio.run(engine.dispose())

def auth(uid):
    return {'Authorization': 'Bearer ' + session_token(uid)}

def test_numbers_and_spoofed_headers_cannot_read(client):
    for rid in (1,2,3,999):
        r=client.get(f'/api/v1/reports/{rid}?current_user_id=d1', headers={'X-User-Id':'d1','X-User-Role':'doctor'})
        assert r.status_code == 404

@pytest.mark.parametrize('uid,status', [('p1',200),('d1',200),('p2',404),('d2',404)])
def test_owner_and_linked_doctor_only(client, uid, status):
    assert client.get('/api/v1/reports/1',headers=auth(uid)).status_code == status

def test_share_token_is_report_scoped_and_not_a_login(client):
    r=client.post('/api/v1/reports/1/share',headers=auth('d1'))
    assert r.status_code == 200
    token=r.json()['token']
    assert client.get('/api/v1/reports/1',headers={'X-Report-Token':token}).status_code == 200
    assert client.get('/api/v1/reports/2',headers={'X-Report-Token':token}).status_code == 404
    assert client.get('/api/v1/invite/my-patients',headers={'Authorization':'Bearer '+token}).status_code == 401
    assert client.post('/api/v1/reports/1/share',headers=auth('p2')).status_code == 404

def test_expired_or_tampered_share_rejected(client):
    expired=create_access_token({'sub':'1','purpose':'report_share'},expires_minutes=-1)
    for token in (expired, report_token(1)+'broken', session_token('p1')):
        assert client.get('/api/v1/reports/1',headers={'X-Report-Token':token}).status_code == 404

def test_profile_role_cannot_be_overridden(client):
    h=auth('p2'); h['X-User-Role']='doctor'; h['X-User-Id']='d1'
    assert client.get('/api/v1/reports/1?current_user_id=d1',headers=h).status_code == 404

def test_assign_cannot_steal_other_doctor_report(client):
    r=client.post('/api/v1/invite/assign-report',json={'report_id':2,'patient_id':'p1'},headers=auth('d1'))
    assert r.status_code == 404
    assert client.get('/api/v1/reports/2',headers=auth('d2')).status_code == 200

def test_password_migration_and_login(client):
    async def inspect():
        async with client.sessions() as db:
            return (await db.execute(text("SELECT phone,password_hash FROM users_profiles WHERE user_id='d1'"))).fetchone()
    phone, hashed=asyncio.run(inspect())
    assert phone is None and hashed != 'old-password'
    assert verify_password('old-password',hashed)
    assert not verify_password('wrong',hashed)
    r=client.post('/api/v1/custom-auth/login',json={'email':'d1@test.example','password':'old-password'})
    assert r.status_code==200 and r.json()['access_token']
    assert client.get('/api/v1/reports/1',headers={'Authorization':'Bearer '+r.json()['access_token']}).status_code==200

def test_new_password_is_hashed(client):
    r=client.post('/api/v1/custom-auth/register',json={'full_name':'New Doctor','email':'new@test.example','password':'new-password','clinic_password':custom_auth.CLINIC_PASSWORD})
    assert r.status_code==200
    async def inspect():
        async with client.sessions() as db:
            return (await db.execute(text("SELECT phone,password_hash FROM users_profiles WHERE email='new@test.example'"))).fetchone()
    phone,hashed=asyncio.run(inspect())
    assert phone is None and verify_password('new-password',hashed)

def test_extended_and_save_require_login(client):
    assert client.post('/api/v1/analysis/extended-recommendations',json={'report_id':1}).status_code==401
    assert client.post('/api/v1/analysis/extended-recommendations',json={'report_id':1},headers=auth('p2')).status_code==404
    assert client.post('/api/v1/reports/save',json={'user_id':'p1'}).status_code==401
    r=client.post('/api/v1/reports/save',json={'user_id':'p1'},headers=auth('p2'))
    assert r.status_code==200
    assert client.get('/api/v1/reports/'+str(r.json()['id']),headers=auth('p1')).status_code==404

def test_verification_rate_limit(client):
    for _ in range(10):
        assert client.post('/api/v1/custom-auth/patient/verify-code',json={'email':'p1@test.example','code':'000000'}).status_code==400
    assert client.post('/api/v1/custom-auth/patient/verify-code',json={'email':'p1@test.example','code':'000000'}).status_code==429

def test_codes_are_hashed_and_single_use(client):
    from services.email_codes import issue_code, verify_code
    async def check():
        async with client.sessions() as db:
            code=await issue_code(db,'p1@test.example','patient_login')
            await db.commit()
            stored=(await db.execute(text("SELECT code FROM email_codes"))).scalar()
            assert stored != code
            assert await verify_code(db,'p1@test.example',code,'patient_login')
            await db.commit()
            assert not await verify_code(db,'p1@test.example',code,'patient_login')
    asyncio.run(check())

def test_patient_access_checked_before_ai(client):
    r=client.post('/api/v1/analysis/analyze',json={'image':'fake','patient_id':'p2'},headers=auth('d1'))
    assert r.status_code==403

def test_analysis_saves_patient_atomically_and_anonymous_receipt(client, monkeypatch):
    import services.teeth_analysis as ta
    import services.pixel_analysis as px
    async def locate(*a,**k): return {'is_teeth':True,'valid_teeth':0}
    async def recommend(*a,**k): return {'is_teeth':True,'has_dye':True,'recommendations':['test'],'recommendations_en':[], 'recommendations_source':'rules','orthodontic_detected':False,'orthodontic_type':None}
    monkeypatch.setattr(ta,'locate_teeth',locate)
    monkeypatch.setattr(ta,'detect_ortho_and_recommend',recommend)
    monkeypatch.setattr(px,'analyze_teeth_pixels',lambda *a,**k: {'tooth_coverage_percent':30,'stained_area_percent':30,'overall_color_percentages':{'white':70,'purple':30,'blue':0,'light_blue':0},'method':'pixel_hsv_v1','teeth':{}})
    monkeypatch.setattr(analysis,'store_image',lambda x:x)
    r=client.post('/api/v1/analysis/analyze',json={'image':'fake','patient_id':'p1'},headers=auth('d1'))
    assert r.status_code==200, r.text
    assert r.json()['saved'] is True and r.json()['analysis_quality']=='limited'
    rid=r.json()['report_id']
    assert client.get(f'/api/v1/reports/{rid}',headers=auth('p1')).status_code==200
    anon=client.post('/api/v1/analysis/analyze',json={'image':'fake'}).json()
    assert anon['report_token']
    assert client.get(f"/api/v1/reports/{anon['report_id']}").status_code==404
    assert client.get(f"/api/v1/reports/{anon['report_id']}",headers={'X-Report-Token':anon['report_token']}).status_code==200
    original_db = client.app.dependency_overrides[get_db]
    class FailSave:
        def __init__(self, db): self.db = db
        def __getattr__(self, name): return getattr(self.db, name)
        async def execute(self, statement, *args, **kwargs):
            if 'INSERT INTO reports' in str(statement):
                raise RuntimeError('simulated storage failure')
            return await self.db.execute(statement, *args, **kwargs)
    async def failing_db():
        async with client.sessions() as db:
            yield FailSave(db)
    client.app.dependency_overrides[get_db] = failing_db
    failed_save = client.post('/api/v1/analysis/analyze',json={'image':'fake'}).json()
    assert failed_save['saved'] is False and failed_save['report_id'] is None
    client.app.dependency_overrides[get_db] = original_db
    async def unavailable(*a, **k): return None
    monkeypatch.setattr(ta,'locate_teeth',unavailable)
    assert client.post('/api/v1/analysis/analyze',json={'image':'fake'}).status_code==503

def test_generated_routes_cannot_bypass_permissions(client):
    from main import app
    app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
    try:
        real = TestClient(app)
        for path in ('/api/v1/entities/users_profiles', '/api/v1/entities/doctor_patients'):
            assert real.get(path).status_code == 401
            assert real.get(path, headers=auth('d1')).status_code == 403
        assert real.post('/api/v1/aihub/gentxt',json={}).status_code == 401
        response = real.get('/api/v1/reports/1', headers=auth('p1'))
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert real.get('/api/v1/reports/1').json() == real.get('/api/v1/reports/999').json()
    finally:
        app.dependency_overrides.clear()

def test_different_analysis_methods_are_not_compared(client):
    async def check():
        async with client.sessions() as db:
            await db.execute(text("UPDATE reports SET analysis_type='z_index_pixel', analysis_data=:data WHERE id=1"), {'data':json.dumps({'method':'pixel_hsv_v1','pollution_percentage':20})})
            await db.commit()
            assert await analysis._previous_progress(db,'p1',{'method':'pixel_hsv_frames_wb_v3'}) is None
    asyncio.run(check())

def test_expired_and_untrusted_session_tokens_rejected(client):
    for token in (session_token('missing-user'), create_access_token({'sub':'d1','purpose':'session'},expires_minutes=-1), 'unsigned-token'):
        assert client.get('/api/v1/reports/1',headers={'Authorization':'Bearer '+token}).status_code == 401
