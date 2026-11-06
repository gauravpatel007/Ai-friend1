import { Conversation, Message, ModelInfo, VoiceStatus, CompanionProfile, ChatAttachment } from '../types';

const BASE_URL = '/api';

export async function fetchHealth(): Promise<{ status: string; companion: string; ws_clients: number }> {
  const res = await fetch(`${BASE_URL}/health`);
  return res.json();
}

export async function fetchConfig(): Promise<Record<string, any>> {
  const res = await fetch(`${BASE_URL}/config`);
  return res.json();
}

export async function updateConfig(key: string, value: any): Promise<void> {
  await fetch(`${BASE_URL}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  });
}

export async function updateConfigBatch(settings: Record<string, any>): Promise<void> {
  await fetch(`${BASE_URL}/config/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  });
}

export async function resetConfigToDefaults(): Promise<Record<string, any>> {
  const res = await fetch(`${BASE_URL}/config/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return res.json();
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${BASE_URL}/conversations`);
  return res.json();
}

export async function createConversation(title?: string): Promise<Conversation> {
  const res = await fetch(`${BASE_URL}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title || 'New Chat' }),
  });
  return res.json();
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await fetch(`${BASE_URL}/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`${BASE_URL}/conversations/${id}`, {
    method: 'DELETE',
  });
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const res = await fetch(`${BASE_URL}/conversations/${conversationId}/messages`);
  return res.json();
}

export async function sendMessage(
  conversationId: string,
  content: string,
  isVoice = false,
  requestId?: string,
  clientTimestamp?: number,
  attachments?: ChatAttachment[],
  images?: string[]
): Promise<{ user_message_id: number; assistant_message_id: number; generation_id: number; request_id?: string; backend_received_time?: number; status?: string; message?: string }> {
  console.log('[BOUNDARY] Request sent: POST /api/conversations/' + conversationId + '/messages');
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 35000);

  try {
    const res = await fetch(`${BASE_URL}/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        content,
        is_voice: isVoice,
        request_id: requestId,
        client_timestamp: clientTimestamp,
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
        images: images && images.length > 0 ? images : undefined,
      }),
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText || res.statusText}`);
    }
    return res.json();
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error('Backend request timed out after 35s. Please check if Ollama or the local server is responsive.');
    }
    throw err;
  }
}

export async function uploadFile(file: File): Promise<{ status: string; attachment: ChatAttachment }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function uploadMultipleFiles(files: File[]): Promise<{ status: string; attachments: ChatAttachment[] }> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  const res = await fetch(`${BASE_URL}/upload/multiple`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteUpload(attachmentId: string): Promise<{ status: string; deleted: boolean }> {
  const res = await fetch(`${BASE_URL}/upload/${encodeURIComponent(attachmentId)}`, {
    method: 'DELETE',
  });
  return res.json();
}

export async function executeRecoveryAction(
  action: string,
  payload?: Record<string, any>
): Promise<{ status: string; action: string; [key: string]: any }> {
  const res = await fetch(`${BASE_URL}/recovery/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  });
  return res.json();
}

export async function clearMessages(conversationId: string): Promise<void> {
  await fetch(`${BASE_URL}/conversations/${conversationId}/messages`, {
    method: 'DELETE',
  });
}

export async function deleteMessage(
  messageId: number,
  pair: boolean = true
): Promise<{ status: string; deleted: boolean; message_ids: number[] }> {
  const q = new URLSearchParams({ pair: String(pair) });
  const res = await fetch(`${BASE_URL}/messages/${messageId}?${q.toString()}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete message: HTTP ${res.status}`);
  }
  return res.json();
}

export async function editMessage(
  messageId: number,
  content: string
): Promise<{ status: string; id: number; content: string }> {
  const res = await fetch(`${BASE_URL}/messages/${messageId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    throw new Error(`Failed to edit message: HTTP ${res.status}`);
  }
  return res.json();
}

export async function retryMessage(
  messageId: number,
  prompt?: string
): Promise<{ status: string; assistant_message_id: number; generation_id: number }> {
  const res = await fetch(`${BASE_URL}/messages/${messageId}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    throw new Error(`Failed to retry message: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchModels(): Promise<ModelInfo> {
  const res = await fetch(`${BASE_URL}/models`);
  return res.json();
}

export async function selectModel(model: string): Promise<void> {
  await fetch(`${BASE_URL}/models/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
}

export async function fetchModelPreferences(): Promise<any> {
  const res = await fetch(`${BASE_URL}/models/preferences`);
  return res.json();
}

export async function updateModelPreferences(prefs: Record<string, any>): Promise<void> {
  await fetch(`${BASE_URL}/models/preferences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  });
}

export async function fetchVoiceStatus(): Promise<VoiceStatus> {
  const res = await fetch(`${BASE_URL}/voice/status`);
  return res.json();
}

export async function toggleVoice(): Promise<{ status: string; mode: string }> {
  const res = await fetch(`${BASE_URL}/voice/toggle`, {
    method: 'POST',
  });
  return res.json();
}

export async function setVoiceMode(mode: string): Promise<{ status: string; mode: string }> {
  const res = await fetch(`${BASE_URL}/voice/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  return res.json();
}

export async function startPushToTalk(): Promise<{ status: string; recording: boolean }> {
  const res = await fetch(`${BASE_URL}/voice/ptt/start`, {
    method: 'POST',
  });
  return res.json();
}

export async function stopPushToTalk(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/voice/ptt/stop`, {
    method: 'POST',
  });
  return res.json();
}

export async function stopVoice(): Promise<void> {
  await fetch(`${BASE_URL}/voice/stop`, {
    method: 'POST',
  });
}

export async function muteVoice(muted: boolean): Promise<void> {
  await fetch(`${BASE_URL}/voice/mute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ muted }),
  });
}

export async function testVoice(text?: string, profileId?: string, language?: string): Promise<void> {
  await fetch(`${BASE_URL}/voice/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, profile_id: profileId, language: language || 'en' }),
  });
}

export async function previewVoice(profileId: string, language: string = 'en', text?: string): Promise<void> {
  await fetch(`${BASE_URL}/voice/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, language, text }),
  });
}

export async function fetchVoiceProfiles(): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/voice/profiles`);
  const data = await res.json();
  return data.profiles || [];
}

export async function setVoiceEngine(engine: string): Promise<void> {
  await fetch(`${BASE_URL}/voice/engine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ engine }),
  });
}

export async function setVoiceSpeed(speed: number): Promise<void> {
  await fetch(`${BASE_URL}/voice/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  });
}

export async function setVoiceVolume(volume: number): Promise<void> {
  await fetch(`${BASE_URL}/voice/volume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ volume }),
  });
}

export async function fetchAudioDevices(): Promise<{ input_devices: string[]; output_devices: string[] }> {
  const res = await fetch(`${BASE_URL}/voice/devices`);
  return res.json();
}

export async function cancelAi(): Promise<void> {
  await fetch(`${BASE_URL}/ai/cancel`, {
    method: 'POST',
  });
}

export async function fetchCompanionState(): Promise<CompanionProfile> {
  const res = await fetch(`${BASE_URL}/companion/state`);
  return res.json();
}

export async function exportChat(conversationId: string): Promise<{ markdown: string; title: string; file_path?: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 6000);
  try {
    const res = await fetch(`${BASE_URL}/chat/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId || '' }),
      signal: controller.signal,
    });
    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchPetStatus(): Promise<{ always_on_top: boolean; visible: boolean; character: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);
  try {
    const res = await fetch(`${BASE_URL}/pet/status`, { signal: controller.signal });
    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function setPetTopmost(alwaysOnTop: boolean): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);
  try {
    await fetch(`${BASE_URL}/pet/topmost`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ always_on_top: alwaysOnTop }),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function togglePetVisible(visible: boolean): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);
  try {
    await fetch(`${BASE_URL}/pet/${visible ? 'show' : 'hide'}`, {
      method: 'POST',
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function resetPetPosition(): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);
  try {
    await fetch(`${BASE_URL}/pet/reset_position`, {
      method: 'POST',
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchDiagnosticStatus(): Promise<any> {
  const res = await fetch(`${BASE_URL}/diagnostic/status`);
  return res.json();
}

export async function toggleDiagnosticMode(enabled?: boolean): Promise<{ status: string; enabled: boolean; diagnostic: any }> {
  const res = await fetch(`${BASE_URL}/diagnostic/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export interface MemoryItem {
  id: string;
  category: string;
  content: string;
  created_at: string;
}

export async function fetchMemories(search?: string): Promise<MemoryItem[]> {
  const url = search ? `${BASE_URL}/memories?search=${encodeURIComponent(search)}` : `${BASE_URL}/memories`;
  const res = await fetch(url);
  return res.json();
}

export async function createMemory(category: string, content: string): Promise<{ status: string; memory: MemoryItem }> {
  const res = await fetch(`${BASE_URL}/memories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, content }),
  });
  return res.json();
}

export async function deleteMemory(memoryId: string): Promise<void> {
  await fetch(`${BASE_URL}/memories/${memoryId}`, {
    method: 'DELETE',
  });
}

export async function setMessageFeedback(
  messageId: number,
  feedback: 'like' | 'dislike' | null,
  conversationId?: string | null
): Promise<{ status: string; message_id: number; feedback: 'like' | 'dislike' | null }> {
  const endpoint = conversationId
    ? `${BASE_URL}/conversations/${encodeURIComponent(conversationId)}/messages/${messageId}/feedback`
    : `${BASE_URL}/messages/${messageId}/feedback`;
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback }),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to update feedback: ${errorText || res.statusText}`);
  }
  return res.json();
}

export async function copyToClipboard(text: string): Promise<{ status: string; copied: boolean }> {
  try {
    const res = await fetch(`${BASE_URL}/clipboard/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      return res.json();
    }
  } catch (err) {
    console.debug('Native clipboard API call note:', err);
  }
  return { status: 'fallback', copied: false };
}

export async function sleepCompanion(): Promise<{ status: string; operational_state: string }> {
  try {
    const res = await fetch(`${BASE_URL}/companion/sleep`, {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
    });
    return res.json();
  } catch (err) {
    console.warn('sleepCompanion request timed out or failed:', err);
    return { status: 'ok', operational_state: 'sleeping' };
  }
}

export async function wakeCompanion(): Promise<{ status: string; operational_state: string }> {
  try {
    const res = await fetch(`${BASE_URL}/companion/wake`, {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
    });
    return res.json();
  } catch (err) {
    console.warn('wakeCompanion request timed out or failed:', err);
    return { status: 'ok', operational_state: 'active' };
  }
}

export async function muteCompanion(): Promise<{ status: string; operational_state: string }> {
  try {
    const res = await fetch(`${BASE_URL}/companion/mute`, {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
    });
    return res.json();
  } catch (err) {
    console.warn('muteCompanion request timed out or failed:', err);
    return { status: 'ok', operational_state: 'muted' };
  }
}

export async function unmuteCompanion(): Promise<{ status: string; operational_state: string }> {
  try {
    const res = await fetch(`${BASE_URL}/companion/unmute`, {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
    });
    return res.json();
  } catch (err) {
    console.warn('unmuteCompanion request timed out or failed:', err);
    return { status: 'ok', operational_state: 'active' };
  }
}

export interface LanguagePreviewResult {
  language: string;
  format: string;
  user_sample: string;
  preview_text: string;
  description: string;
}

export async function fetchLanguagePreview(language = 'gu', format = 'native'): Promise<LanguagePreviewResult> {
  const params = new URLSearchParams({ language, format });
  const res = await fetch(`${BASE_URL}/language/preview?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch language preview: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchTTSCapability(language = 'auto'): Promise<{
  supported: boolean;
  engine_name: string;
  target_language: string;
  language_name: string;
  status_badge: string;
  message: string;
}> {
  const params = new URLSearchParams({ language });
  const res = await fetch(`${BASE_URL}/voice/capability?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch TTS capability: ${res.statusText}`);
  }
  return res.json();
}

