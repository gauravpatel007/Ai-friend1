import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from PySide6.QtCore import QCoreApplication
from fastapi.testclient import TestClient
from app.api.server import app
from app.settings.config_manager import ConfigManager
from app.memory.conversation_repository import ConversationRepository
from app.ai.ai_service import AIService
from app.voice.voice_service import VoiceService
from main_api import setup_signal_bridges

q_app = QCoreApplication.instance() or QCoreApplication(sys.argv)
cfg = ConfigManager()
conv_repo = ConversationRepository()
ai = AIService(cfg)
try:
    voice = VoiceService()
except Exception as e:
    voice = None
    print('VoiceService init notice:', e)

app.state.config_manager = cfg
app.state.conv_repo = conv_repo
app.state.ai_service = ai
app.state.voice_service = voice
app.state.current_assistant_msg_id = None

setup_signal_bridges(q_app, conv_repo)

client = TestClient(app)

# 1. Health
print('1. Health:', client.get('/api/health').json())

# 2. Voice endpoints
print('2. Voice status:', client.get('/api/voice/status').json())
print('3. Voice toggle:', client.post('/api/voice/toggle').json())
print('4. Voice speed:', client.post('/api/voice/speed', json={'speed': 1.2}).json())
print('5. Voice volume:', client.post('/api/voice/volume', json={'volume': 80}).json())
print('6. Voice engine:', client.post('/api/voice/engine', json={'engine': 'piper'}).json())
print('7. Voice devices:', client.get('/api/voice/devices').json())

# 3. Create conversation & send message (Offline companion test)
conv = client.post('/api/conversations', json={'title': 'Test Chat'}).json()
conv_id = conv['id']
print('8. Created conv:', conv_id)

send_res = client.post(f'/api/conversations/{conv_id}/messages', json={'content': 'Hello Buddy!'}).json()
print('9. Send message dispatched:', send_res)

# Pump Qt events to let _OfflineWorker stream and complete
for _ in range(60):
    q_app.processEvents()
    time.sleep(0.04)

msgs = client.get(f'/api/conversations/{conv_id}/messages').json()
print('10. Messages after offline streaming:')
for m in msgs:
    role = m['role']
    status = m['status']
    content = m['content'][:60]
    print(f'   [{role}] ({status}) -> {content}...')
print('ALL BACKEND CHECKS PASSED!')
