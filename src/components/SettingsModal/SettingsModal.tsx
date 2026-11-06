import React, { useState, useEffect } from 'react';
import {
  Sliders,
  Server,
  User,
  Sparkles,
  Volume2,
  Database,
  Palette,
  Activity,
  X,
  Check,
  Plus,
  Trash2,
  Search,
  Play,
  RotateCcw,
  Shield,
  Layers,
  Maximize2,
  Minimize2,
  Film,
  Key,
  Eye,
  EyeOff,
  ShieldCheck,
  AlertCircle,
  Globe,
  ExternalLink,
  Link,
  ChevronRight,
  Tv,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import * as api from '../../api/http';
import {
  fetchTMDBKeyStatus,
  TMDBKeyStatusResponse,
  fetchHDHub4uStatus,
  HDHub4uStatusResponse,
  fetchWatchProviderTemplates,
} from '../../api/movieApi';
import { TMDBConfigModal } from './TMDBConfigModal';
import { HDHub4uConfigModal } from './HDHub4uConfigModal';
import { WatchProvidersConfigModal } from './WatchProvidersConfigModal';
import { MemoryItem } from '../../types';
import './SettingsModal.css';

type SettingsCategory =
  | 'general'
  | 'language'
  | 'model'
  | 'voice'
  | 'personality'
  | 'memory'
  | 'appearance'
  | 'movie_hub'
  | 'diagnostics';

export const SettingsModal: React.FC = () => {
  const {
    isSettingsOpen,
    setSettingsOpen,
    settingsInitialCategory,
    companionProfile,
    modelInfo,
    voiceStatus,
    selectModel,
    setVoiceEngine,
    setVoiceSpeed,
    setVoiceVolume,
    testVoice,
    previewVoice,
    diagnosticMode,
    diagnosticStatus,
    setDiagnosticMode,
  } = useChatStore();

  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('general');
  const [isMaximized, setIsMaximized] = useState(false);

  // Movie Hub States & Sub-Modal Dialogs
  const [isTmdbModalOpen, setIsTmdbModalOpen] = useState(false);
  const [isHdhubModalOpen, setIsHdhubModalOpen] = useState(false);
  const [isWatchProvidersModalOpen, setIsWatchProvidersModalOpen] = useState(false);
  const [tmdbStatus, setTmdbStatus] = useState<TMDBKeyStatusResponse | null>(null);
  const [hdhubStatus, setHdhubStatus] = useState<HDHub4uStatusResponse | null>(null);
  const [watchCustomCount, setWatchCustomCount] = useState<number>(0);

  const loadTmdbStatus = async () => {
    try {
      const res = await fetchTMDBKeyStatus();
      setTmdbStatus(res);
    } catch (e) {
      console.error('Failed to load TMDB key status:', e);
    }
  };

  const loadHdhubStatus = async () => {
    try {
      const res = await fetchHDHub4uStatus();
      setHdhubStatus(res);
    } catch (e) {
      console.error('Failed to load HDHub4u status:', e);
    }
  };

  const loadWatchProvidersStatus = async () => {
    try {
      const res = await fetchWatchProviderTemplates();
      setWatchCustomCount(res.custom_count || 0);
    } catch (e) {
      console.error('Failed to load watch provider templates status:', e);
    }
  };

  // Form State
  const [ollamaHost, setOllamaHost] = useState('http://127.0.0.1:11434');
  const [companionName, setCompanionName] = useState(companionProfile.name || 'Buddy');
  const [personality, setPersonality] = useState('friendly');
  const [selectedModel, setSelectedModel] = useState('llama3.2:3b');
  const [ttsEngine, setTtsEngine] = useState('kokoro');
  const [selectedVoiceProfile, setSelectedVoiceProfile] = useState('arjun');
  const [personaVoiceMap, setPersonaVoiceMap] = useState<Record<string, string>>({
    friendly: 'arjun',
    concise: 'kabir',
    playful: 'zara',
    academic: 'kabir',
  });
  const [speed, setSpeed] = useState(1.0);
  const [volume, setVolume] = useState(85);
  const [launchOnStartup, setLaunchOnStartup] = useState(false);
  const [acrylicEnabled, setAcrylicEnabled] = useState(true);
  const [accentColor, setAccentColor] = useState('#0A84FF');
  const [isTestingVoice, setIsTestingVoice] = useState(false);
  const [previewLanguage, setPreviewLanguage] = useState<'en' | 'hi' | 'gu'>('en');
  const [activePreviewVoiceId, setActivePreviewVoiceId] = useState<string | null>(null);
  const [perVoiceLang, setPerVoiceLang] = useState<Record<string, 'en' | 'hi' | 'gu'>>({
    arjun: 'en',
    kabir: 'en',
    ananya: 'en',
    mira: 'en',
    zara: 'en',
  });
  const [isResetting, setIsResetting] = useState(false);

  // Model Settings & Preferences (Phase 5)
  const [modelSelectionMode, setModelSelectionMode] = useState<'auto' | 'manual'>('auto');
  const [responsePriority, setResponsePriority] = useState<'fastest' | 'balanced' | 'quality'>('balanced');
  const [taskPreferences, setTaskPreferences] = useState<{
    general_conversation: string;
    complex_reasoning: string;
    coding: string;
    document_summarization: string;
    vision: string;
  }>({
    general_conversation: 'auto',
    complex_reasoning: 'auto',
    coding: 'auto',
    document_summarization: 'auto',
    vision: 'auto',
  });
  const [compatibleModelsByTask, setCompatibleModelsByTask] = useState<Record<string, string[]>>({});
  const [isManualModelAvailable, setIsManualModelAvailable] = useState<boolean>(true);

  // Language & Communication States
  const [responseLanguage, setResponseLanguage] = useState<string>('auto');
  const [responseFormat, setResponseFormat] = useState<string>('native');
  const [voiceOutputLanguage, setVoiceOutputLanguage] = useState<string>('follow_response');
  const [specificVoiceLanguage, setSpecificVoiceLanguage] = useState<string>('en');
  const [sttLanguage, setSttLanguage] = useState<string>('auto');
  const [livePreview, setLivePreview] = useState<{
    user_sample: string;
    preview_text: string;
    description: string;
  }>({
    user_sample: 'Tamaru naam su che?',
    preview_text: 'નમસ્તે! હું બોન્ડ છું. આજે તમે કેમ છો?',
    description: 'Auto-detect dynamically mirrors your input language.',
  });

  useEffect(() => {
    let active = true;
    api.fetchLanguagePreview(responseLanguage, responseFormat)
      .then((data) => {
        if (active && data) {
          setLivePreview({
            user_sample: data.user_sample,
            preview_text: data.preview_text,
            description: data.description,
          });
        }
      })
      .catch(() => {
        if (!active) return;
        if (responseLanguage === 'gu') {
          setLivePreview({
            user_sample: responseFormat === 'romanized' ? 'Tamaru naam su che?' : 'તમારું નામ શું છે?',
            preview_text: responseFormat === 'romanized' ? 'Namaste! Hu Bond chu. Aaje Tame Kem cho?' : 'નમસ્તે! હું બોન્ડ છું. આજે તમે કેમ છો?',
            description: 'Gujarati communication preview',
          });
        }
      });
    return () => {
      active = false;
    };
  }, [responseLanguage, responseFormat]);

  // Memory Tab State
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memorySearch, setMemorySearch] = useState('');
  const [newMemContent, setNewMemContent] = useState('');
  const [newMemCategory, setNewMemCategory] = useState('preference');
  const [isAddingMemory, setIsAddingMemory] = useState(false);

  // Notice
  const [savedNotice, setSavedNotice] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const applyAppearanceStyles = (acrylic: boolean, accent: string) => {
    try {
      document.documentElement.setAttribute('data-acrylic', String(acrylic));
      document.documentElement.style.setProperty(
        '--backdrop-blur',
        acrylic ? 'blur(24px) saturate(180%)' : 'none'
      );
      document.documentElement.style.setProperty('--color-system-blue', accent);
      document.documentElement.style.setProperty('--color-system-blue-glow', `${accent}40`);
      document.documentElement.style.setProperty('--color-border-focused', `${accent}88`);
    } catch (e) {
      console.warn('Could not apply appearance styles to document:', e);
    }
  };

  // Close SettingsModal on Escape key if no sub-modal is open
  useEffect(() => {
    if (!isSettingsOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isTmdbModalOpen && !isHdhubModalOpen && !isWatchProvidersModalOpen) {
        setSettingsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSettingsOpen, isTmdbModalOpen, isHdhubModalOpen, isWatchProvidersModalOpen, setSettingsOpen]);

  useEffect(() => {
    if (!isSettingsOpen) return;
    let isMounted = true;

    // Fetch model preferences (Phase 5)
    api.fetchModelPreferences().then((prefs) => {
      if (!isMounted || !prefs) return;
      if (prefs.model_selection_mode) setModelSelectionMode(prefs.model_selection_mode);
      if (prefs.response_priority) setResponsePriority(prefs.response_priority);
      if (prefs.task_preferred_models) {
        setTaskPreferences((prev) => ({ ...prev, ...prefs.task_preferred_models }));
      }
      if (prefs.compatible_models_by_task) {
        setCompatibleModelsByTask(prefs.compatible_models_by_task);
      }
      if (prefs.is_manual_model_available !== undefined) {
        setIsManualModelAvailable(Boolean(prefs.is_manual_model_available));
      }
      if (prefs.active_model) {
        setSelectedModel(prefs.active_model);
      }
    }).catch((e) => console.warn('Could not load model preferences:', e));

    // Fetch config
    api.fetchConfig().then((cfg) => {
      if (!isMounted || !cfg) return;

      const host = cfg.ai?.ollama_host ?? cfg['ai.ollama_host'];
      if (host) setOllamaHost(host);

      const name =
        cfg.ai?.companion_name ??
        cfg['ai.companion_name'] ??
        cfg.companion?.name ??
        cfg['companion.name'] ??
        cfg.character?.name ??
        cfg['character.name'] ??
        companionProfile.name;
      if (name) setCompanionName(name);

      const pers = cfg.ai?.personality ?? cfg['ai.personality'];
      if (pers) setPersonality(pers);

      const pvm = cfg.ai?.persona_voice_map ?? cfg['ai.persona_voice_map'];
      if (pvm && typeof pvm === 'object') {
        setPersonaVoiceMap(prev => ({ ...prev, ...pvm }));
      }

      const mdl = cfg.ai?.model ?? cfg['ai.model'] ?? modelInfo.active_model;
      if (mdl) setSelectedModel(mdl);

      const engine = cfg.voice?.tts_engine ?? cfg.voice?.engine ?? cfg['voice.tts_engine'] ?? cfg['voice.engine'];
      if (engine) setTtsEngine(engine);

      const spd = cfg.voice?.speed ?? cfg.voice?.voice_speed ?? cfg['voice.speed'] ?? cfg['voice.voice_speed'];
      if (spd !== undefined && spd !== null) setSpeed(Number(spd));

      const vol = cfg.voice?.volume ?? cfg['voice.volume'];
      if (vol !== undefined && vol !== null) {
        const numVol = Number(vol);
        setVolume(numVol <= 1.0 ? Math.round(numVol * 100) : Math.round(numVol));
      }

      const startup = cfg.general?.start_at_login ?? cfg.general?.start_with_windows ?? cfg['general.start_at_login'] ?? cfg['general.start_with_windows'];
      if (startup !== undefined && startup !== null) setLaunchOnStartup(Boolean(startup));

      const acrylic = cfg.ui?.acrylic_enabled ?? cfg['ui.acrylic_enabled'];
      const isAc = acrylic !== undefined && acrylic !== null ? Boolean(acrylic) : true;
      setAcrylicEnabled(isAc);

      const accent = cfg.ui?.accent_color ?? cfg['ui.accent_color'] ?? '#0A84FF';
      setAccentColor(accent);

      applyAppearanceStyles(isAc, accent);

      // Load Language Configuration
      const langCfg = cfg.language ?? {};
      const respLang = langCfg.response_language ?? cfg['language.response_language'];
      if (respLang) {
        setResponseLanguage(respLang);
      } else {
        setResponseLanguage('auto');
      }
      const respFmt = langCfg.response_format ?? cfg['language.response_format'];
      if (respFmt) setResponseFormat(respFmt);
      const voiceOut = langCfg.voice_output_language ?? cfg['language.voice_output_language'];
      if (voiceOut) setVoiceOutputLanguage(voiceOut);
      const specVoice = langCfg.specific_voice_language ?? cfg['language.specific_voice_language'];
      if (specVoice) setSpecificVoiceLanguage(specVoice);
      const stt = langCfg.stt_language ?? cfg['language.stt_language'] ?? cfg.voice?.language ?? cfg['voice.language'];
      if (stt) setSttLanguage(stt);
    }).catch(() => {});

    // Fetch memories
    api.fetchMemories().then((res) => {
      if (isMounted && Array.isArray(res)) setMemories(res);
    }).catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [isSettingsOpen, modelInfo.active_model]);

  if (!isSettingsOpen) return null;

  const handleAccentChange = (col: string) => {
    setAccentColor(col);
    applyAppearanceStyles(acrylicEnabled, col);
  };

  const handleAcrylicChange = (enabled: boolean) => {
    setAcrylicEnabled(enabled);
    applyAppearanceStyles(enabled, accentColor);
  };

  const handlePreviewVoice = async (profileId: string, lang?: string) => {
    const targetLang = lang || perVoiceLang[profileId] || previewLanguage || 'en';
    setActivePreviewVoiceId(profileId);
    setIsTestingVoice(true);
    try {
      if (setVoiceEngine && ttsEngine) await setVoiceEngine(ttsEngine);
      if (setVoiceSpeed && speed) await setVoiceSpeed(speed);
      const volNormalized = volume > 1 ? volume / 100 : volume;
      if (setVoiceVolume && volNormalized !== undefined) await setVoiceVolume(volNormalized);
      if (previewVoice) {
        await previewVoice(profileId, targetLang);
      } else {
        await testVoice(undefined, profileId, targetLang);
      }
    } catch (err) {
      console.error('Failed to preview voice:', err);
    } finally {
      setTimeout(() => {
        setIsTestingVoice(false);
        setActivePreviewVoiceId(null);
      }, 2000);
    }
  };

  const handleTestSpeech = async () => {
    await handlePreviewVoice(selectedVoiceProfile, previewLanguage);
  };

  const handleResetDefaults = async () => {
    if (!window.confirm('Reset all settings to default configuration? This will restore standard parameters.')) {
      return;
    }
    setIsResetting(true);
    try {
      await api.resetConfigToDefaults();
      setOllamaHost('http://127.0.0.1:11434');
      setCompanionName('Buddy');
      setPersonality('friendly');
      setSelectedVoiceProfile('arjun');
      setPersonaVoiceMap({
        friendly: 'arjun',
        concise: 'kabir',
        playful: 'zara',
        academic: 'kabir',
      });
      setSelectedModel('llama3.2:3b');
      setTtsEngine('kokoro');
      setSpeed(1.0);
      setVolume(85);
      setLaunchOnStartup(false);
      setAcrylicEnabled(true);
      setAccentColor('#0A84FF');
      applyAppearanceStyles(true, '#0A84FF');
      setResponseLanguage('auto');
      setResponseFormat('native');
      setVoiceOutputLanguage('follow_response');
      setSpecificVoiceLanguage('en');
      setSttLanguage('auto');

      setSavedNotice(true);
      setTimeout(() => setSavedNotice(false), 1500);
    } catch (err) {
      console.error('Failed to reset config to defaults:', err);
    } finally {
      setIsResetting(false);
    }
  };

  const handleSave = async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      const volNormalized = volume > 1 ? volume / 100 : volume;

      const trimmedName = companionName.trim() || 'Buddy';
      const batchSettings: Record<string, any> = {
        'ai.ollama_host': ollamaHost,
        'ai.companion_name': trimmedName,
        'companion.name': trimmedName,
        'character.name': trimmedName,
        'ai.personality': personality,
        'ai.persona_voice_map': personaVoiceMap,
        'ai.model': selectedModel,
        'ai.model_selection_mode': modelSelectionMode,
        'ai.auto_model_routing': modelSelectionMode === 'auto',
        'ai.response_priority': responsePriority,
        'ai.task_preferred_models': taskPreferences,
        'voice.selected_profile': selectedVoiceProfile,
        'voice.engine': ttsEngine,
        'voice.tts_engine': ttsEngine,
        'voice.voice_speed': speed,
        'voice.speed': speed,
        'voice.volume': volNormalized,
        'general.start_at_login': launchOnStartup,
        'general.start_with_windows': launchOnStartup,
        'ui.acrylic_enabled': acrylicEnabled,
        'ui.accent_color': accentColor,
        'language.response_language': responseLanguage,
        'language.response_format': responseFormat,
        'language.voice_output_language': voiceOutputLanguage,
        'language.specific_voice_language': specificVoiceLanguage,
        'language.stt_language': sttLanguage,
        'voice.language': sttLanguage,
      };

      await api.updateConfigBatch(batchSettings);

      // Synchronize runtime voice parameters in store
      try {
        if (setVoiceEngine && ttsEngine) await setVoiceEngine(ttsEngine);
        if (setVoiceSpeed && speed) await setVoiceSpeed(speed);
        if (setVoiceVolume && volNormalized !== undefined) await setVoiceVolume(volNormalized);
      } catch (voiceErr) {
        console.warn('Voice parameter update warning:', voiceErr);
      }

      if (trimmedName) {
        useChatStore.setState((s) => ({
          companionProfile: {
            ...s.companionProfile,
            name: trimmedName,
          },
        }));
        document.title = `AI Desktop Friend — Desktop Companion - ${trimmedName}`;
        if (window.dispatchEvent) {
          window.dispatchEvent(new CustomEvent('companion-name-changed', { detail: trimmedName }));
        }
      }

      if (selectedModel && selectedModel !== modelInfo.active_model) {
        try {
          await selectModel(selectedModel);
        } catch (err) {
          console.warn('Model switch warning:', err);
        }
      }

      try {
        await api.updateModelPreferences({
          model_selection_mode: modelSelectionMode,
          response_priority: responsePriority,
          task_preferred_models: taskPreferences,
          manual_model: selectedModel,
        });
      } catch (prefErr) {
        console.warn('Model preferences update warning:', prefErr);
      }

      setSavedNotice(true);
      setTimeout(() => {
        setSavedNotice(false);
        setSettingsOpen(false);
      }, 700);
    } catch (e) {
      console.error('Failed to save settings', e);
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddMemory = async () => {
    const content = newMemContent.trim();
    if (!content) return;
    try {
      const res = await api.createMemory(newMemCategory, content);
      if (res && res.memory) {
        setMemories((prev) => [res.memory, ...prev]);
        setNewMemContent('');
        setIsAddingMemory(false);
      }
    } catch (e) {
      console.error('Failed to add memory', e);
      alert('Failed to save memory. Please verify backend is running.');
    }
  };

  const handleDeleteMemory = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this memory?')) {
      return;
    }
    try {
      await api.deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch (e) {
      console.error('Failed to delete memory', e);
    }
  };

  useEffect(() => {
    if (isSettingsOpen) {
      if (settingsInitialCategory) {
        setActiveCategory(settingsInitialCategory as SettingsCategory);
      }
      loadTmdbStatus();
      loadHdhubStatus();
      loadWatchProvidersStatus();
    }
  }, [isSettingsOpen, settingsInitialCategory]);

  useEffect(() => {
    if (activeCategory === 'movie_hub') {
      loadTmdbStatus();
      loadHdhubStatus();
      loadWatchProvidersStatus();
    }
  }, [activeCategory]);

  const filteredMemories = memories.filter(
    (m) =>
      m.content.toLowerCase().includes(memorySearch.toLowerCase()) ||
      m.category.toLowerCase().includes(memorySearch.toLowerCase())
  );

  return (
    <div
      className="apple-settings-scrim"
      onClick={(e) => {
        // Prevent closing main settings window if sub-modals are currently open
        if (isTmdbModalOpen || isHdhubModalOpen || isWatchProvidersModalOpen) {
          e.stopPropagation();
          return;
        }
        setSettingsOpen(false);
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`apple-settings-window ${isMaximized ? 'is-maximized' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Window Header */}
        <div
          className="settings-window-header"
          onDoubleClick={() => setIsMaximized((prev) => !prev)}
          title="Double-click header to maximize or restore"
        >
          <div className="settings-window-titlebar">
            <div className="sheet-badge-icon">
              <Sliders size={16} className="sheet-title-icon" />
            </div>
            <div className="sheet-title-texts">
              <h2 className="settings-main-title">Settings</h2>
              <span className="settings-sub-caption">Configure local AI model, speech, and companion preferences</span>
            </div>
          </div>
          <div className="settings-window-actions">
            <button
              className="settings-window-action-btn"
              onClick={() => setIsMaximized((prev) => !prev)}
              title={isMaximized ? 'Restore Window' : 'Maximize Window'}
              aria-label={isMaximized ? 'Restore Window' : 'Maximize Window'}
            >
              {isMaximized ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>
            <button
              className="settings-window-close"
              onClick={() => setSettingsOpen(false)}
              aria-label="Close Settings"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Window Body: Master-Detail Layout */}
        <div className="settings-window-body">
          {/* Left Category Sidebar */}
          <aside className="settings-category-sidebar">
            <nav className="settings-nav-group">
              <button
                className={`category-item ${activeCategory === 'general' ? 'active' : ''}`}
                onClick={() => setActiveCategory('general')}
              >
                <div className="squircle-badge badge-blue">
                  <User size={15} />
                </div>
                <span>General</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'model' ? 'active' : ''}`}
                onClick={() => setActiveCategory('model')}
              >
                <div className="squircle-badge badge-purple">
                  <Server size={15} />
                </div>
                <span>AI Model</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'language' ? 'active' : ''}`}
                onClick={() => setActiveCategory('language')}
              >
                <div className="squircle-badge badge-teal">
                  <Globe size={15} />
                </div>
                <span>Language &amp; Communication</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'voice' ? 'active' : ''}`}
                onClick={() => setActiveCategory('voice')}
              >
                <div className="squircle-badge badge-cyan">
                  <Volume2 size={15} />
                </div>
                <span>Voice &amp; Audio</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'personality' ? 'active' : ''}`}
                onClick={() => setActiveCategory('personality')}
              >
                <div className="squircle-badge badge-amber">
                  <Sparkles size={15} />
                </div>
                <span>Personality</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'memory' ? 'active' : ''}`}
                onClick={() => setActiveCategory('memory')}
              >
                <div className="squircle-badge badge-green">
                  <Database size={15} />
                </div>
                <span>Long-Term Memory</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'appearance' ? 'active' : ''}`}
                onClick={() => setActiveCategory('appearance')}
              >
                <div className="squircle-badge badge-pink">
                  <Palette size={15} />
                </div>
                <span>Appearance</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'movie_hub' ? 'active' : ''}`}
                onClick={() => setActiveCategory('movie_hub')}
              >
                <div className="squircle-badge badge-indigo">
                  <Film size={15} />
                </div>
                <span>Movie Hub</span>
              </button>

              <button
                className={`category-item ${activeCategory === 'diagnostics' ? 'active' : ''}`}
                onClick={() => setActiveCategory('diagnostics')}
              >
                <div className="squircle-badge badge-orange">
                  <Activity size={15} />
                </div>
                <span>Diagnostics</span>
              </button>
            </nav>
          </aside>

          {/* Right Content Area */}
          <section className="settings-detail-pane">
            {/* 1. GENERAL TAB */}
            {activeCategory === 'general' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">General Settings</h3>
                <p className="pane-section-desc">Manage companion identity and desktop behaviors.</p>

                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Companion Name</span>
                      <span className="setting-caption">Name used across conversation headers and speech</span>
                    </div>
                    <input
                      type="text"
                      className="apple-input-text"
                      value={companionName}
                      onChange={(e) => setCompanionName(e.target.value)}
                      placeholder="Buddy"
                    />
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Start with Windows</span>
                      <span className="setting-caption">Automatically launch AI Companion on login</span>
                    </div>
                    <label className="apple-switch">
                      <input
                        type="checkbox"
                        checked={launchOnStartup}
                        onChange={(e) => setLaunchOnStartup(e.target.checked)}
                      />
                      <span className="switch-slider" />
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* 2. AI MODEL TAB (Phase 5) */}
            {activeCategory === 'model' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Local AI Model &amp; Inference</h3>
                <p className="pane-section-desc">Zero cloud APIs. Connects exclusively to your local Ollama daemon with automatic task routing.</p>

                {/* Card 1: Selection Mode */}
                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Model Selection Mode</span>
                      <span className="setting-caption">
                        {modelSelectionMode === 'auto'
                          ? 'Automatic: Bond dynamically analyzes requests and routes to the best installed model.'
                          : 'Manual: Bond strictly uses your chosen model without automatic switching.'}
                      </span>
                    </div>
                    <select
                      className="apple-select"
                      value={modelSelectionMode}
                      onChange={(e) => setModelSelectionMode(e.target.value as 'auto' | 'manual')}
                    >
                      <option value="auto">Automatic (Intelligent Router)</option>
                      <option value="manual">Manual (Strict Selection)</option>
                    </select>
                  </div>

                  {modelSelectionMode === 'manual' && (
                    <>
                      <div className="setting-row">
                        <div className="setting-meta">
                          <span className="setting-title">Manual Active Model</span>
                          <span className="setting-caption">Fixed model for all incoming queries</span>
                        </div>
                        <select
                          className="apple-select"
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                        >
                          {Array.from(
                            new Set([
                              ...modelInfo.available_models,
                              selectedModel,
                            ].filter(Boolean))
                          ).map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </div>

                      {!isManualModelAvailable && (
                        <div style={{
                          margin: '6px 14px 12px',
                          padding: '10px 14px',
                          borderRadius: '8px',
                          background: 'rgba(255, 69, 58, 0.12)',
                          border: '1px solid rgba(255, 69, 58, 0.3)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          fontSize: '12px',
                          color: '#FF453A',
                        }}>
                          <AlertCircle size={15} />
                          <span>
                            Selected model <strong>{selectedModel}</strong> is currently unavailable in Ollama. Please select an installed model.
                          </span>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Card 2: Response Priority (Automatic Mode) */}
                {modelSelectionMode === 'auto' && (
                  <div className="apple-grouped-inset" style={{ marginTop: '16px' }}>
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Response Priority</span>
                        <span className="setting-caption">
                          Determines whether the router prioritizes rapid first token speed or analytical benchmark quality.
                        </span>
                      </div>
                      <select
                        className="apple-select"
                        value={responsePriority}
                        onChange={(e) => setResponsePriority(e.target.value as 'fastest' | 'balanced' | 'quality')}
                      >
                        <option value="fastest">⚡ Fastest Response (Low latency, smaller models)</option>
                        <option value="balanced">⚖️ Balanced (Recommended balance of speed &amp; quality)</option>
                        <option value="quality">🧠 Best Available Quality (Highest reasoning &amp; benchmark capacity)</option>
                      </select>
                    </div>
                  </div>
                )}

                {/* Card 3: Task-Specific Model Preferences (Automatic Mode) */}
                {modelSelectionMode === 'auto' && (
                  <div className="apple-grouped-inset" style={{ marginTop: '16px' }}>
                    <div style={{ padding: '14px 16px 8px' }}>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#FFFFFF' }}>Task-Specific Model Preferences</span>
                      <p style={{ fontSize: '11px', color: '#8E8E93', margin: '3px 0 0' }}>
                        Override router selection with your preferred model per task. Only compatible installed models are displayed.
                      </p>
                    </div>

                    {/* General Conversation */}
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">General Conversation</span>
                        <span className="setting-caption">Everyday chatting, greetings, and quick facts</span>
                      </div>
                      <select
                        className="apple-select"
                        value={taskPreferences.general_conversation || 'auto'}
                        onChange={(e) => setTaskPreferences((p) => ({ ...p, general_conversation: e.target.value }))}
                      >
                        <option value="auto">Auto (Router Decides)</option>
                        {(compatibleModelsByTask['general_conversation'] || []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>

                    {/* Complex Reasoning */}
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Complex Reasoning</span>
                        <span className="setting-caption">Step-by-step logic, math, and analytical deduction</span>
                      </div>
                      <select
                        className="apple-select"
                        value={taskPreferences.complex_reasoning || 'auto'}
                        onChange={(e) => setTaskPreferences((p) => ({ ...p, complex_reasoning: e.target.value }))}
                      >
                        <option value="auto">Auto (Router Decides)</option>
                        {(compatibleModelsByTask['complex_reasoning'] || []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                        {(!compatibleModelsByTask['complex_reasoning'] || compatibleModelsByTask['complex_reasoning'].length === 0) && (
                          <option disabled value="none">No verified reasoning model installed</option>
                        )}
                      </select>
                    </div>

                    {/* Coding */}
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Coding &amp; Debugging</span>
                        <span className="setting-caption">Code generation, refactoring, and bug diagnosis</span>
                      </div>
                      <select
                        className="apple-select"
                        value={taskPreferences.coding || 'auto'}
                        onChange={(e) => setTaskPreferences((p) => ({ ...p, coding: e.target.value }))}
                      >
                        <option value="auto">Auto (Router Decides)</option>
                        {(compatibleModelsByTask['coding'] || []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                        {(!compatibleModelsByTask['coding'] || compatibleModelsByTask['coding'].length === 0) && (
                          <option disabled value="none">No verified coding model installed</option>
                        )}
                      </select>
                    </div>

                    {/* Document Summarization */}
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Document Summarization</span>
                        <span className="setting-caption">Long documents, text condensation, and long-form writing</span>
                      </div>
                      <select
                        className="apple-select"
                        value={taskPreferences.document_summarization || 'auto'}
                        onChange={(e) => setTaskPreferences((p) => ({ ...p, document_summarization: e.target.value }))}
                      >
                        <option value="auto">Auto (Router Decides)</option>
                        {(compatibleModelsByTask['document_summarization'] || []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>

                    {/* Vision & Image Understanding */}
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Vision &amp; Image Understanding</span>
                        <span className="setting-caption">Multimodal visual image inspection and diagram queries</span>
                      </div>
                      <select
                        className="apple-select"
                        value={taskPreferences.vision || 'auto'}
                        onChange={(e) => setTaskPreferences((p) => ({ ...p, vision: e.target.value }))}
                      >
                        <option value="auto">Auto (Router Decides)</option>
                        {(compatibleModelsByTask['vision'] || []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                        {(!compatibleModelsByTask['vision'] || compatibleModelsByTask['vision'].length === 0) && (
                          <option disabled value="none">No verified vision model installed</option>
                        )}
                      </select>
                    </div>
                  </div>
                )}

                {/* Card 4: Local Daemon Status & Host */}
                <div className="apple-grouped-inset" style={{ marginTop: '16px' }}>
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Ollama API Host</span>
                      <span className="setting-caption">Local loopback host and port</span>
                    </div>
                    <input
                      type="text"
                      className="apple-input-text"
                      value={ollamaHost}
                      onChange={(e) => setOllamaHost(e.target.value)}
                      placeholder="http://127.0.0.1:11434"
                    />
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Local Daemon Status</span>
                      <span className="setting-caption">Daemon availability on 127.0.0.1</span>
                    </div>
                    <span className={`status-pill ${modelInfo.is_online ? 'pill-online' : 'pill-offline'}`}>
                      {modelInfo.is_online ? 'Online (Local)' : 'Service Unreachable'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* LANGUAGE & COMMUNICATION TAB */}
            {activeCategory === 'language' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Language &amp; Communication</h3>
                <p className="pane-section-desc">Configure multilingual input understanding, response language, script display, and voice output.</p>

                {/* Card 1: AI Response Generation & Text Format */}
                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">AI Response Language</span>
                      <span className="setting-caption">Bond will respond in this selected language, or mirror your language in Auto-detect mode.</span>
                    </div>
                    <select
                      className="apple-select"
                      value={responseLanguage}
                      onChange={(e) => setResponseLanguage(e.target.value)}
                    >
                      <option value="auto">Auto-detect (Recommended)</option>
                      <option value="en">English</option>
                      <option value="gu">Gujarati (ગુજરાતી)</option>
                      <option value="hi">Hindi (हिन्दी)</option>
                      <option value="mr">Marathi (मराठी)</option>
                      <option value="bn">Bengali (বাংলা)</option>
                      <option value="ta">Tamil (தமிழ்)</option>
                      <option value="te">Telugu (తెలుగు)</option>
                      <option value="pa">Punjabi (ਪੰਜਾਬੀ)</option>
                      <option value="es">Spanish (Español)</option>
                      <option value="fr">French (Français)</option>
                      <option value="de">German (Deutsch)</option>
                      <option value="ja">Japanese (日本語)</option>
                      <option value="zh">Chinese (中文)</option>
                    </select>
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Display Response Text As</span>
                      <span className="setting-caption">Romanized keeps regional languages written in Latin letters without translating into English.</span>
                    </div>
                    <select
                      className="apple-select"
                      value={responseFormat}
                      onChange={(e) => setResponseFormat(e.target.value)}
                    >
                      <option value="native">Native Script (Recommended) — e.g. તારું નામ શું છે?</option>
                      <option value="romanized">Romanized / Latin Script — e.g. Tamaru naam su che?</option>
                    </select>
                  </div>

                  {/* Live Script & Language Preview Card */}
                  <div style={{
                    margin: '10px 14px 14px',
                    padding: '12px 14px',
                    background: 'rgba(10, 132, 255, 0.08)',
                    borderRadius: '10px',
                    border: '1px solid rgba(10, 132, 255, 0.2)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Sparkles size={13} style={{ color: '#0A84FF' }} />
                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#0A84FF', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Live Script &amp; Language Preview
                        </span>
                      </div>
                      <span style={{ fontSize: '10.5px', color: '#8E8E93' }}>
                        {livePreview.description}
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px', lineHeight: 1.45 }}>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <span style={{ color: '#8E8E93', minWidth: '40px' }}>You:</span>
                        <span style={{ color: '#F5F5F7', fontWeight: 500 }}>
                          {livePreview.user_sample}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <span style={{ color: '#0A84FF', minWidth: '40px', fontWeight: 600 }}>Bond:</span>
                        <span style={{ color: '#32D74B', fontWeight: 600 }}>
                          {livePreview.preview_text}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Card 2: Voice Output Language & Live Limitation Check */}
                <div className="apple-grouped-inset" style={{ marginTop: '16px' }}>
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Voice Output Language</span>
                      <span className="setting-caption">Language used by the speech synthesis engine for spoken responses.</span>
                    </div>
                    <select
                      className="apple-select"
                      value={voiceOutputLanguage}
                      onChange={(e) => setVoiceOutputLanguage(e.target.value)}
                    >
                      <option value="follow_response">Follow AI Response Language (Recommended)</option>
                      <option value="follow_input">Follow My Input Language</option>
                      <option value="specific">Select a Specific Language</option>
                    </select>
                  </div>

                  {voiceOutputLanguage === 'specific' && (
                    <div className="setting-row">
                      <div className="setting-meta">
                        <span className="setting-title">Specific Voice Language</span>
                        <span className="setting-caption">Explicit voice language override for speech synthesis.</span>
                      </div>
                      <select
                        className="apple-select"
                        value={specificVoiceLanguage}
                        onChange={(e) => setSpecificVoiceLanguage(e.target.value)}
                      >
                        <option value="en">English</option>
                        <option value="gu">Gujarati (ગુજરાતી)</option>
                        <option value="hi">Hindi (हिन्दी)</option>
                        <option value="mr">Marathi (मराठी)</option>
                        <option value="bn">Bengali (বাংলা)</option>
                        <option value="ta">Tamil (தமிழ்)</option>
                        <option value="te">Telugu (తెలుగు)</option>
                        <option value="pa">Punjabi (ਪੰਜਾਬੀ)</option>
                        <option value="es">Spanish (Español)</option>
                        <option value="fr">French (Français)</option>
                        <option value="de">German (Deutsch)</option>
                        <option value="ja">Japanese (日本語)</option>
                        <option value="zh">Chinese (中文)</option>
                      </select>
                    </div>
                  )}

                  {/* Live TTS Limitation Check & Status Card */}
                  <div style={{
                    margin: '12px 14px',
                    padding: '12px 14px',
                    background: 'rgba(0, 0, 0, 0.25)',
                    borderRadius: '10px',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#F5F5F7' }}>TTS Engine Compatibility Status:</span>
                      {(((voiceOutputLanguage === 'follow_response' && responseLanguage === 'gu') || voiceOutputLanguage === 'gu' || (voiceOutputLanguage === 'specific' && specificVoiceLanguage === 'gu')) && ttsEngine !== 'sapi5_with_gu') ? (
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          color: '#FF9F0A',
                          background: 'rgba(255, 159, 10, 0.15)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          border: '1px solid rgba(255, 159, 10, 0.4)',
                        }}>
                          Voice Limitation
                        </span>
                      ) : (
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          color: '#32D74B',
                          background: 'rgba(50, 215, 75, 0.15)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          border: '1px solid rgba(50, 215, 75, 0.4)',
                        }}>
                          Supported
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: '11px', color: '#8E8E93', margin: 0, lineHeight: 1.4 }}>
                      {(((voiceOutputLanguage === 'follow_response' && responseLanguage === 'gu') || voiceOutputLanguage === 'gu' || (voiceOutputLanguage === 'specific' && specificVoiceLanguage === 'gu')))
                        ? `The active ${ttsEngine.toUpperCase()} voice engine currently has English loaded. Gujarati voice synthesis will use authentic phonetic Latin vocalization or safe speech fallback, while chat responses will display in your configured Gujarati format.`
                        : `The active ${ttsEngine.toUpperCase()} voice engine supports speech synthesis for the requested language.`}
                    </p>
                  </div>
                </div>

                {/* Card 3: Speech Recognition Language */}
                <div className="apple-grouped-inset" style={{ marginTop: '16px' }}>
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Speech Recognition Language</span>
                      <span className="setting-caption">Controls speech recognition. Automatic detection accurately recognizes speech across English, Gujarati, Hindi, and multilingual code-switching.</span>
                    </div>
                    <select
                      className="apple-select"
                      value={sttLanguage}
                      onChange={(e) => setSttLanguage(e.target.value)}
                    >
                      <option value="auto">Auto-detect (English, Gujarati, Hindi)</option>
                      <option value="en">English</option>
                      <option value="gu">Gujarati (ગુજરાતી)</option>
                      <option value="hi">Hindi (हिन्दी)</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* 3. VOICE & AUDIO TAB */}
            {activeCategory === 'voice' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Speech Recognition &amp; Synthesis</h3>
                <p className="pane-section-desc">Multi-tier local speech architecture (Faster-Whisper &amp; Kokoro / Piper / SAPI5).</p>

                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Companion Voice Profile</span>
                      <span className="setting-caption">Bond's distinct voice persona (2 male, 3 female)</span>
                    </div>
                    <select
                      className="apple-select"
                      value={selectedVoiceProfile}
                      onChange={(e) => setSelectedVoiceProfile(e.target.value)}
                    >
                      <option value="arjun">Arjun – Male (Natural, friendly, confident)</option>
                      <option value="kabir">Kabir – Male (Calm, mature, composed)</option>
                      <option value="ananya">Ananya – Female (Warm, friendly, expressive)</option>
                      <option value="mira">Mira – Female (Calm, soft, gentle)</option>
                      <option value="zara">Zara – Female (Energetic, confident, lively)</option>
                    </select>
                  </div>

                  <div className="voice-profiles-container" style={{ padding: '0 16px 8px 16px' }}>
                    {[
                      { id: 'arjun', name: 'Arjun', gender: 'Male', tone: 'Natural, friendly, confident pace' },
                      { id: 'kabir', name: 'Kabir', gender: 'Male', tone: 'Calm, mature, composed delivery' },
                      { id: 'ananya', name: 'Ananya', gender: 'Female', tone: 'Warm, expressive, natural pace' },
                      { id: 'mira', name: 'Mira', gender: 'Female', tone: 'Gentle, calm, soft & relaxed pace' },
                      { id: 'zara', name: 'Zara', gender: 'Female', tone: 'Energetic, confident, lively delivery' },
                    ].map((vp) => (
                      <div
                        key={vp.id}
                        className={`voice-profile-card ${selectedVoiceProfile === vp.id ? 'selected' : ''}`}
                        onClick={() => setSelectedVoiceProfile(vp.id)}
                      >
                        <div className="voice-card-left">
                          <div className="voice-radio-circle">
                            {selectedVoiceProfile === vp.id && <div className="voice-radio-dot" />}
                          </div>
                          <div>
                            <div className="voice-meta-title-row">
                              <span className="voice-name">{vp.name}</span>
                              <span className="voice-gender-badge">{vp.gender}</span>
                            </div>
                            <div className="voice-traits">{vp.tone}</div>
                          </div>
                        </div>
                        <div className="voice-card-right" onClick={(e) => e.stopPropagation()}>
                          <select
                            className="voice-lang-select"
                            value={perVoiceLang[vp.id] || 'en'}
                            onChange={(e) => setPerVoiceLang(prev => ({ ...prev, [vp.id]: e.target.value as any }))}
                          >
                            <option value="en">English</option>
                            <option value="hi">हिन्दी</option>
                            <option value="gu">ગુજરાતી</option>
                          </select>
                          <button
                            type="button"
                            className="voice-preview-btn"
                            disabled={isTestingVoice}
                            onClick={() => {
                              setSelectedVoiceProfile(vp.id);
                              handlePreviewVoice(vp.id, perVoiceLang[vp.id] || 'en');
                            }}
                          >
                            <Play size={12} className={activePreviewVoiceId === vp.id ? 'spinning' : ''} />
                            <span>{activePreviewVoiceId === vp.id ? 'Playing...' : 'Test Voice'}</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Text-to-Speech Engine</span>
                      <span className="setting-caption">Local synthesis fallback chain</span>
                    </div>
                    <select
                      className="apple-select"
                      value={ttsEngine}
                      onChange={(e) => setTtsEngine(e.target.value)}
                    >
                      <option value="kokoro">Kokoro-82M (Neural High Quality)</option>
                      <option value="piper">Piper (Fast Neural ONNX)</option>
                      <option value="sapi5">Windows SAPI5 (Native Offline)</option>
                    </select>
                  </div>

                  <div className="setting-row-column">
                    <div className="slider-header-row">
                      <span className="setting-title">Speech Speed</span>
                      <span className="slider-value-badge">{speed.toFixed(2)}x</span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="2.0"
                      step="0.05"
                      value={speed}
                      onChange={(e) => setSpeed(parseFloat(e.target.value))}
                      className="apple-slider"
                    />
                  </div>

                  <div className="setting-row-column">
                    <div className="slider-header-row">
                      <span className="setting-title">Speech Volume</span>
                      <span className="slider-value-badge">{volume}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      value={volume}
                      onChange={(e) => setVolume(parseInt(e.target.value, 10))}
                      className="apple-slider"
                    />
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Test Audio Playback</span>
                      <span className="setting-caption">
                        Synthesize test sentence for active voice ({selectedVoiceProfile.toUpperCase()} • {previewLanguage.toUpperCase()})
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <select
                        className="voice-lang-select"
                        value={previewLanguage}
                        onChange={(e) => setPreviewLanguage(e.target.value as any)}
                      >
                        <option value="en">English</option>
                        <option value="hi">हिन्दी</option>
                        <option value="gu">ગુજરાતી</option>
                      </select>
                      <button
                        type="button"
                        className="apple-secondary-btn"
                        onClick={handleTestSpeech}
                        disabled={isTestingVoice}
                      >
                        <Play size={14} className={isTestingVoice && !activePreviewVoiceId ? 'spinning' : ''} />
                        <span>{isTestingVoice && !activePreviewVoiceId ? 'Synthesizing...' : 'Test Voice'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 4. PERSONALITY TAB */}
            {activeCategory === 'personality' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Companion Personality &amp; Tone</h3>
                <p className="pane-section-desc">Shape the behavioral demeanor and conversational tone.</p>

                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Persona Preset</span>
                      <span className="setting-caption">System prompt behavioral instructions</span>
                    </div>
                    <select
                      className="apple-select"
                      value={personality}
                      onChange={(e) => {
                        const newPers = e.target.value;
                        setPersonality(newPers);
                        const assignedVoice = personaVoiceMap[newPers] || 'arjun';
                        setSelectedVoiceProfile(assignedVoice);
                      }}
                    >
                      <option value="friendly">Friendly &amp; Supportive (Warm &amp; Encouraging)</option>
                      <option value="concise">Concise &amp; Professional (Direct &amp; Efficient)</option>
                      <option value="playful">Playful &amp; Humorous (Witty &amp; Lighthearted)</option>
                      <option value="academic">Academic &amp; Analytical (Detailed &amp; Precise)</option>
                    </select>
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Assigned Voice Profile</span>
                      <span className="setting-caption">Voice profile used when this persona is active (Phase 2.1, 2.2)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <select
                        className="apple-select"
                        value={personaVoiceMap[personality] || selectedVoiceProfile || 'arjun'}
                        onChange={(e) => {
                          const newVoice = e.target.value;
                          setPersonaVoiceMap(prev => ({ ...prev, [personality]: newVoice }));
                          setSelectedVoiceProfile(newVoice);
                        }}
                      >
                        <option value="arjun">Arjun – Male (Natural, friendly, confident)</option>
                        <option value="kabir">Kabir – Male (Calm, mature, composed)</option>
                        <option value="ananya">Ananya – Female (Warm, friendly, expressive)</option>
                        <option value="mira">Mira – Female (Calm, soft, gentle)</option>
                        <option value="zara">Zara – Female (Energetic, confident, lively)</option>
                      </select>
                      <button
                        type="button"
                        className="apple-secondary-btn"
                        onClick={() => handlePreviewVoice(personaVoiceMap[personality] || selectedVoiceProfile || 'arjun')}
                        disabled={isTestingVoice}
                        title="Test voice for this persona"
                      >
                        <Play size={13} className={isTestingVoice && activePreviewVoiceId === (personaVoiceMap[personality] || selectedVoiceProfile || 'arjun') ? 'spinning' : ''} />
                        <span>Test Voice</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 5. LONG-TERM MEMORY TAB */}
            {activeCategory === 'memory' && (
              <div className="settings-section-content">
                <div className="pane-header-with-action">
                  <div>
                    <h3 className="pane-section-heading">Long-Term Memory Persistence</h3>
                    <p className="pane-section-desc">Facts, user preferences, and memories stored in local SQLite FTS5.</p>
                  </div>
                  <button
                    className="apple-primary-btn"
                    onClick={() => setIsAddingMemory(true)}
                  >
                    <Plus size={14} />
                    <span>Add Memory</span>
                  </button>
                </div>

                {isAddingMemory && (
                  <div className="add-memory-card">
                    <div className="add-memory-header">
                      <span>Add New Long-Term Fact</span>
                      <button className="icon-btn-subtle" onClick={() => setIsAddingMemory(false)}>
                        <X size={14} />
                      </button>
                    </div>
                    <select
                      className="apple-select mb-2"
                      value={newMemCategory}
                      onChange={(e) => setNewMemCategory(e.target.value)}
                    >
                      <option value="preference">Preference</option>
                      <option value="project">Project</option>
                      <option value="fact">Fact</option>
                      <option value="learning">Learning</option>
                      <option value="general">General</option>
                    </select>
                    <textarea
                      className="apple-textarea"
                      placeholder="e.g., User's name is Bond and prefers Python over Java."
                      value={newMemContent}
                      onChange={(e) => setNewMemContent(e.target.value)}
                      rows={3}
                    />
                    <div className="add-memory-actions">
                      <button className="apple-secondary-btn" onClick={() => setIsAddingMemory(false)}>
                        Cancel
                      </button>
                      <button className="apple-primary-btn" onClick={handleAddMemory}>
                        Save Memory
                      </button>
                    </div>
                  </div>
                )}

                <div className="memory-search-bar">
                  <Search size={14} className="search-icon" />
                  <input
                    type="text"
                    placeholder="Search memories by keyword..."
                    value={memorySearch}
                    onChange={(e) => setMemorySearch(e.target.value)}
                    className="memory-search-input"
                  />
                </div>

                <div className="memories-list-scroll">
                  {filteredMemories.length === 0 ? (
                    <div className="empty-memory-state">
                      <Database size={28} className="empty-icon" />
                      <span>No long-term memories found.</span>
                    </div>
                  ) : (
                    filteredMemories.map((mem) => (
                      <div key={mem.id} className="memory-item-card">
                        <div className="memory-item-main">
                          <span className={`memory-cat-pill cat-${mem.category}`}>
                            {mem.category}
                          </span>
                          <p className="memory-content-text">{mem.content}</p>
                          <span className="memory-date-caption">{mem.created_at}</span>
                        </div>
                        <button
                          className="memory-delete-btn"
                          onClick={() => handleDeleteMemory(mem.id)}
                          title="Delete memory"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* 6. APPEARANCE TAB */}
            {activeCategory === 'appearance' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Appearance &amp; Window Materials</h3>
                <p className="pane-section-desc">Tailor frosted glass translucency and accent color palettes.</p>

                <div className="apple-grouped-inset">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">VisionOS Frosted Acrylic</span>
                      <span className="setting-caption">High-fidelity backdrop blurs and specular borders</span>
                    </div>
                    <label className="apple-switch">
                      <input
                        type="checkbox"
                        checked={acrylicEnabled}
                        onChange={(e) => handleAcrylicChange(e.target.checked)}
                      />
                      <span className="switch-slider" />
                    </label>
                  </div>

                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">System Accent Color</span>
                      <span className="setting-caption">Theme color for active tabs and bubbles</span>
                    </div>
                    <div className="color-swatch-row">
                      {['#0A84FF', '#00E5FF', '#30D158', '#BF5AF2', '#FF9F0A'].map((col) => (
                        <button
                          key={col}
                          type="button"
                          className={`color-swatch-btn ${accentColor === col ? 'swatch-active' : ''}`}
                          style={{ backgroundColor: col }}
                          onClick={() => handleAccentChange(col)}
                          title={`Set accent color to ${col}`}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 8. MOVIE HUB TAB */}
            {activeCategory === 'movie_hub' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Movie Hub &amp; Media Integrations</h3>
                <p className="pane-section-desc">
                  Select an option below to open its dedicated window for credentials, streaming mirrors, and advanced configurations.
                </p>

                <div className="apple-grouped-inset">
                  {/* Option 1: TMDB API Key */}
                  <div
                    className="setting-row setting-row-clickable"
                    onClick={() => setIsTmdbModalOpen(true)}
                    role="button"
                    tabIndex={0}
                    title="Click to open TMDB API key configuration window"
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <div className="settings-submodal-badge badge-indigo">
                        <Key size={18} />
                      </div>
                      <div className="setting-meta">
                        <span className="setting-title" style={{ fontSize: '14.5px', fontWeight: 600 }}>
                          TMDB API Key
                        </span>
                        <span className="setting-caption">
                          {tmdbStatus?.configured
                            ? `Active: ${tmdbStatus.masked_key} (${tmdbStatus.source === 'env' ? '.env Fallback' : 'Custom Key'})`
                            : 'Configure TMDB v3 API key or token'}
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`settings-tmdb-status-pill ${tmdbStatus?.configured ? 'connected' : 'disconnected'}`}>
                        <span className="settings-status-dot" />
                        {tmdbStatus?.configured ? 'Connected & Active' : 'Not Configured'}
                      </span>
                      <ChevronRight size={18} style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                    </div>
                  </div>

                  {/* Option 2: HdHub4u Link */}
                  <div
                    className="setting-row setting-row-clickable"
                    onClick={() => setIsHdhubModalOpen(true)}
                    role="button"
                    tabIndex={0}
                    title="Click to open HdHub4u link & mirror configuration window"
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <div className="settings-submodal-badge badge-purple">
                        <Globe size={18} />
                      </div>
                      <div className="setting-meta">
                        <span className="setting-title" style={{ fontSize: '14.5px', fontWeight: 600 }}>
                          HdHub4u Link
                        </span>
                        <span className="setting-caption">
                          {hdhubStatus?.is_custom
                            ? 'Custom mirror active (dynamic title replacement enabled)'
                            : 'Default (.cl) template active'}
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`settings-tmdb-status-pill ${hdhubStatus?.active_url ? 'connected' : 'disconnected'}`}>
                        <span className="settings-status-dot" />
                        {hdhubStatus?.is_custom ? 'Custom Mirror' : 'Default Active'}
                      </span>
                      <ChevronRight size={18} style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                    </div>
                  </div>

                  {/* Option 3: Where to Watch Links */}
                  <div
                    className="setting-row setting-row-clickable"
                    onClick={() => setIsWatchProvidersModalOpen(true)}
                    role="button"
                    tabIndex={0}
                    title="Click to configure streaming search URL templates (JioHotstar, Netflix, Prime Video, etc.)"
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <div className="settings-submodal-badge badge-teal">
                        <Tv size={18} />
                      </div>
                      <div className="setting-meta">
                        <span className="setting-title" style={{ fontSize: '14.5px', fontWeight: 600 }}>
                          Where to Watch Links
                        </span>
                        <span className="setting-caption">
                          Search templates for JioHotstar, Netflix, Prime Video, Apple TV, and 20+ services
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className="settings-tmdb-status-pill connected">
                        <span className="settings-status-dot" />
                        {watchCustomCount > 0 ? `${watchCustomCount} Custom` : '20+ Active'}
                      </span>
                      <ChevronRight size={18} style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                    </div>
                  </div>
                </div>

                {/* Sub-Card Notice */}
                <div className="settings-security-note" style={{ marginTop: '16px' }}>
                  <ShieldCheck size={14} style={{ color: '#30D158', flexShrink: 0 }} />
                  <span>
                    Clicking any option opens a dedicated window with connection testing, custom URL templates, live title replacement preview, and history management.
                  </span>
                </div>
              </div>
            )}

            {/* 7. DIAGNOSTICS TAB */}
            {activeCategory === 'diagnostics' && (
              <div className="settings-section-content">
                <h3 className="pane-section-heading">Telemetry &amp; Stage Latencies</h3>
                <p className="pane-section-desc">Live performance metrics across all 7 pipeline stages.</p>

                <div className="apple-grouped-inset mb-3">
                  <div className="setting-row">
                    <div className="setting-meta">
                      <span className="setting-title">Diagnostic Instrumentation</span>
                      <span className="setting-caption">Emit [DIAGNOSTIC] and [PERFORMANCE] telemetry</span>
                    </div>
                    <label className="apple-switch">
                      <input
                        type="checkbox"
                        checked={diagnosticMode}
                        onChange={(e) => setDiagnosticMode(e.target.checked)}
                      />
                      <span className="switch-slider" />
                    </label>
                  </div>
                </div>

                <div className="diagnostic-metrics-grid">
                  <div className="metric-card">
                    <span className="metric-label">Audio Capture</span>
                    <span className="metric-val">{diagnosticStatus.audio_duration_sec.toFixed(2)}s</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">STT Latency</span>
                    <span className="metric-val">{(diagnosticStatus.speech_recognition_latency_ms || 0).toFixed(0)} ms</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">Backend Request</span>
                    <span className="metric-val">{(diagnosticStatus.backend_request_latency_ms || 0).toFixed(0)} ms</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">First Token (TTFT)</span>
                    <span className="metric-val">{(diagnosticStatus.model_time_to_first_output_ms || 0).toFixed(0)} ms</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">Total LLM Time</span>
                    <span className="metric-val">{(diagnosticStatus.total_model_generation_ms || 0).toFixed(0)} ms</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">Time to Audible</span>
                    <span className="metric-val">{(diagnosticStatus.time_to_first_audible_response_ms || 0).toFixed(0)} ms</span>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Window Footer Actions */}
        <div className="settings-window-footer">
          <button
            type="button"
            className="apple-secondary-btn"
            style={{ marginRight: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={handleResetDefaults}
            disabled={isResetting || isSaving}
            title="Restore default application configuration"
          >
            <RotateCcw size={13} className={isResetting ? 'spinning' : ''} />
            <span>{isResetting ? 'Resetting...' : 'Reset Defaults'}</span>
          </button>
          <button
            type="button"
            className="apple-secondary-btn"
            onClick={() => setSettingsOpen(false)}
          >
            Cancel
          </button>
          <button
            type="button"
            className="apple-primary-btn"
            onClick={handleSave}
            disabled={isSaving}
          >
            {savedNotice ? (
              <>
                <Check size={14} className="save-icon-success" />
                <span>Saved Changes</span>
              </>
            ) : isSaving ? (
              <span>Saving...</span>
            ) : (
              <span>Save Changes</span>
            )}
          </button>
        </div>
      </div>

      {/* Dedicated TMDB API Key Configuration Window */}
      <TMDBConfigModal
        isOpen={isTmdbModalOpen}
        onClose={() => setIsTmdbModalOpen(false)}
        status={tmdbStatus}
        onStatusChange={(updated) => setTmdbStatus(updated)}
      />

      {/* Dedicated HDHub4u Link & Mirror Configuration Window */}
      <HDHub4uConfigModal
        isOpen={isHdhubModalOpen}
        onClose={() => setIsHdhubModalOpen(false)}
        status={hdhubStatus}
        onStatusChange={(updated) => setHdhubStatus(updated)}
      />

      {/* Dedicated Streaming Where to Watch Configuration Window */}
      <WatchProvidersConfigModal
        isOpen={isWatchProvidersModalOpen}
        onClose={() => setIsWatchProvidersModalOpen(false)}
        onSaved={loadWatchProvidersStatus}
      />
    </div>
  );
};
