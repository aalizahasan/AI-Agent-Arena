from fastapi.testclient import TestClient
from app.main import app

def test_health_is_not_false_integration_success():
    data=TestClient(app).get('/health').json()
    assert data['status']=='ok'
    assert 'not verified' in data['integrations']

def test_frontend_exists_and_routes_via_n8n():
    r=TestClient(app).get('/')
    assert r.status_code==200
    assert 'Good care begins' in r.text
    assert "fetch('/submit'" in r.text

def test_agent_api_is_protected_from_direct_public_calls(monkeypatch):
    monkeypatch.setenv('INTERNAL_API_KEY','this-is-test-secret')
    r=TestClient(app).post('/api/requests',json={'request_id':'ONE','message':'book a visit'})
    assert r.status_code==401
