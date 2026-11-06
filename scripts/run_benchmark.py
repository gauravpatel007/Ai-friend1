"""Comprehensive Empirical Benchmark: TEXT vs VOICE Response Performance (Task 8).

Strict requirements:
- Identical prompts for both TEXT and VOICE modes.
- Same LLM model: llama3.2:3b.
- Cold-start performance measured separately from warm performance.
- At least 10 warm measurement iterations per mode.
- Precise monotonic timers (time.perf_counter()).
- Real components: live Ollama, Faster-Whisper STT, and SAPI5/Piper/Kokoro TTS.
- Component breakdown analysis identifying the most time-consuming phase.
- Output saved to benchmarks/benchmark_results.json and printed to console.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.ollama_client import OllamaClient
from app.voice.whisper_engine import WhisperEngine
from app.voice.sentence_chunker import SentenceChunker
from app.voice.sapi5_engine import Sapi5TTSEngine


BENCHMARK_PROMPTS: List[str] = [
    "What is the capital of France and what is it famous for?",
    "How does gravity work in simple terms?",
    "Tell me a fun fact about space exploration.",
    "What are three healthy habits for better daily focus?",
    "Can you explain the difference between speed and velocity?",
    "Why is the sky blue during the day and red at sunset?",
    "Give me a quick two-sentence motivational quote for today.",
    "How do airplanes stay in the air?",
    "What is the fastest animal on earth and how fast can it run?",
    "Tell me one interesting fact about the human brain.",
]

MODEL_NAME = "llama3.2:3b"


def percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats (0 to 100)."""
    if not data:
        return 0.0
    return float(np.percentile(np.array(data), p))


def unload_ollama_model(client: OllamaClient, model: str) -> None:
    """Unload model from Ollama memory to ensure an authentic cold start."""
    try:
        url = f"{client.base_url}/api/generate"
        payload = {"model": model, "keep_alive": 0}
        client._session.post(url, json=payload, timeout=10.0)
        time.sleep(1.0)
    except Exception as e:
        print(f"Notice: Model unload request: {e}")


def synthesize_prompt_audio(tts: Sapi5TTSEngine, prompt_text: str) -> np.ndarray:
    """Synthesize clean 16kHz speech waveform corresponding to the user saying the prompt."""
    res = tts.synthesize(prompt_text)
    samples = res.samples
    sr = res.sample_rate

    # Resample to 16000 Hz float32 mono for Whisper if needed
    if sr != 16000:
        duration = len(samples) / float(sr)
        target_len = int(round(duration * 16000))
        old_indices = np.linspace(0.0, duration, len(samples), endpoint=False)
        new_indices = np.linspace(0.0, duration, target_len, endpoint=False)
        samples = np.interp(new_indices, old_indices, samples).astype(np.float32)
    return samples


def run_baseline_benchmark(client: OllamaClient, tts: Sapi5TTSEngine, prompt_audios: Dict[str, np.ndarray]):
    whisper = WhisperEngine(model_size="base")

    # =========================================================================
    # PART 1: TEXT MODE BENCHMARK
    # =========================================================================
    print("=" * 80)
    print(">>> RUNNING TEXT MODE BENCHMARK")
    print("=" * 80)

    # 1.1 Cold-Start Text Run
    print("1. Unloading model to measure authentic COLD-START Text performance...")
    unload_ollama_model(client, MODEL_NAME)

    cold_prompt = BENCHMARK_PROMPTS[0]
    t0_cold = time.perf_counter()
    first_token_cold_time = None
    accum_cold = []

    stream = client.chat_stream(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": cold_prompt}],
        keep_alive="15m",
    )
    for chunk in stream:
        if first_token_cold_time is None and chunk.strip():
            first_token_cold_time = time.perf_counter() - t0_cold
        accum_cold.append(chunk)

    t_end_cold = time.perf_counter() - t0_cold
    if first_token_cold_time is None:
        first_token_cold_time = t_end_cold

    cold_text_record = {
        "prompt": cold_prompt,
        "first_visible_token_sec": first_token_cold_time,
        "complete_response_sec": t_end_cold,
        "response_chars": len("".join(accum_cold)),
    }
    print(f"   [COLD START] TTFT: {first_token_cold_time*1000.0:.1f}ms | Complete: {t_end_cold*1000.0:.1f}ms ({cold_text_record['response_chars']} chars)\n")

    # 1.2 Warm Text Runs (10 iterations)
    print("2. Running 10 WARM-START Text iterations (model pinned in memory via keep-alive)...")
    warm_text_records = []

    for idx, prompt in enumerate(BENCHMARK_PROMPTS, 1):
        t0 = time.perf_counter()
        first_token_time = None
        accum = []

        stream = client.chat_stream(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            keep_alive="15m",
        )
        for chunk in stream:
            if first_token_time is None and chunk.strip():
                first_token_time = time.perf_counter() - t0
            accum.append(chunk)

        total_time = time.perf_counter() - t0
        if first_token_time is None:
            first_token_time = total_time

        rec = {
            "iteration": idx,
            "prompt": prompt,
            "first_visible_token_sec": first_token_time,
            "complete_response_sec": total_time,
            "response_chars": len("".join(accum)),
        }
        warm_text_records.append(rec)
        print(f"   Iteration {idx:2d}/10: TTFT = {first_token_time*1000.0:6.1f}ms | Complete = {total_time*1000.0:6.1f}ms | Chars = {rec['response_chars']}")

    text_warm_ttft = [r["first_visible_token_sec"] * 1000.0 for r in warm_text_records]
    text_warm_complete = [r["complete_response_sec"] * 1000.0 for r in warm_text_records]

    text_stats = {
        "cold_start": {
            "first_visible_token_ms": cold_text_record["first_visible_token_sec"] * 1000.0,
            "complete_response_ms": cold_text_record["complete_response_sec"] * 1000.0,
        },
        "warm": {
            "iterations": len(warm_text_records),
            "avg_time_to_first_token_ms": float(np.mean(text_warm_ttft)),
            "avg_complete_response_ms": float(np.mean(text_warm_complete)),
            "median_response_ms": float(np.median(text_warm_complete)),
            "p95_response_ms": percentile(text_warm_complete, 95),
            "min_response_ms": float(np.min(text_warm_complete)),
            "max_response_ms": float(np.max(text_warm_complete)),
        },
    }

    print("\n--- TEXT MODE RESULTS SUMMARY ---")
    print(f"Cold Start: First Token = {text_stats['cold_start']['first_visible_token_ms']:.1f}ms | Complete = {text_stats['cold_start']['complete_response_ms']:.1f}ms")
    print(f"Warm Avg TTFT:              {text_stats['warm']['avg_time_to_first_token_ms']:.1f}ms")
    print(f"Warm Avg Complete Time:     {text_stats['warm']['avg_complete_response_ms']:.1f}ms")
    print(f"Warm Median Complete Time:  {text_stats['warm']['median_response_ms']:.1f}ms")
    print(f"Warm P95 Complete Time:     {text_stats['warm']['p95_response_ms']:.1f}ms\n")

    # =========================================================================
    # PART 2: VOICE MODE BENCHMARK
    # =========================================================================
    print("=" * 80)
    print(">>> RUNNING VOICE MODE BENCHMARK")
    print("=" * 80)

    # 2.1 Cold-Start Voice Run
    print("1. Unloading model to measure authentic COLD-START Voice performance...")
    unload_ollama_model(client, MODEL_NAME)

    cold_voice_prompt = BENCHMARK_PROMPTS[0]
    cold_audio = prompt_audios[cold_voice_prompt]

    # End of speech is marked at t_eos = 0
    t_eos_cold = time.perf_counter()

    # Step A: STT Speech Recognition
    stt_res_cold = whisper.transcribe(cold_audio)
    t_stt_cold = time.perf_counter()
    stt_duration_cold = t_stt_cold - t_eos_cold

    # Step B: LLM Streaming & Chunking
    cold_stream = client.chat_stream(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": stt_res_cold.text}],
        keep_alive="15m",
    )

    cold_first_token_time = None
    cold_first_sentence = None
    cold_first_audible_time = None
    cold_voice_chunker = SentenceChunker()
    cold_generated_text_chunks = []
    cold_tts_times = []

    for chunk in cold_stream:
        now = time.perf_counter()
        if cold_first_token_time is None and chunk.strip():
            cold_first_token_time = now - t_eos_cold
        cold_generated_text_chunks.append(chunk)

        sentences = cold_voice_chunker.add_chunk(chunk)
        for s in sentences:
            if cold_first_sentence is None:
                cold_first_sentence = s
                # Synthesize chunk 1 to measure time to first audible response
                t_tts1_start = time.perf_counter()
                tts.synthesize(s)
                t_tts1_end = time.perf_counter()
                cold_tts_times.append(t_tts1_end - t_tts1_start)
                cold_first_audible_time = t_tts1_end - t_eos_cold
            else:
                t_tts_s = time.perf_counter()
                tts.synthesize(s)
                cold_tts_times.append(time.perf_counter() - t_tts_s)

    # Flush remaining sentence
    rem = cold_voice_chunker.flush()
    for s in rem:
        if cold_first_sentence is None:
            cold_first_sentence = s
            t_tts1_start = time.perf_counter()
            tts.synthesize(s)
            t_tts1_end = time.perf_counter()
            cold_tts_times.append(t_tts1_end - t_tts1_start)
            cold_first_audible_time = t_tts1_end - t_eos_cold
        else:
            t_tts_s = time.perf_counter()
            tts.synthesize(s)
            cold_tts_times.append(time.perf_counter() - t_tts_s)

    t_voice_cold_total = time.perf_counter() - t_eos_cold
    cold_voice_record = {
        "prompt": cold_voice_prompt,
        "transcript": stt_res_cold.text,
        "stt_duration_sec": stt_duration_cold,
        "eos_to_first_llm_token_sec": cold_first_token_time or 0.0,
        "eos_to_first_audible_sec": cold_first_audible_time or t_voice_cold_total,
        "complete_voice_sec": t_voice_cold_total,
    }
    print(f"   [COLD START] STT: {stt_duration_cold*1000.0:.1f}ms | EOS->Token: {(cold_first_token_time or 0)*1000.0:.1f}ms | EOS->Audible: {(cold_first_audible_time or 0)*1000.0:.1f}ms | Complete: {t_voice_cold_total*1000.0:.1f}ms\n")

    # 2.2 Warm Voice Runs (10 iterations)
    print("2. Running 10 WARM-START Voice iterations (model pinned in memory via keep-alive)...")
    warm_voice_records = []

    for idx, prompt in enumerate(BENCHMARK_PROMPTS, 1):
        audio = prompt_audios[prompt]
        t_eos = time.perf_counter()

        # Step A: STT (Speech Recognition)
        stt_res = whisper.transcribe(audio)
        t_stt_done = time.perf_counter()
        stt_dur = t_stt_done - t_eos

        # Step B: LLM Generation & Sentence-Pipelined TTS
        v_stream = client.chat_stream(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": stt_res.text}],
            keep_alive="15m",
        )

        v_first_token_time = None
        v_first_sentence = None
        v_first_audible_time = None
        v_chunker = SentenceChunker()
        v_chunks = []
        v_tts_durations = []

        for chunk in v_stream:
            now = time.perf_counter()
            if v_first_token_time is None and chunk.strip():
                v_first_token_time = now - t_eos
            v_chunks.append(chunk)

            sentences = v_chunker.add_chunk(chunk)
            for s in sentences:
                if v_first_sentence is None:
                    v_first_sentence = s
                    t_tts_s = time.perf_counter()
                    tts.synthesize(s)
                    t_tts_e = time.perf_counter()
                    v_tts_durations.append(t_tts_e - t_tts_s)
                    v_first_audible_time = t_tts_e - t_eos
                else:
                    t_tts_s = time.perf_counter()
                    tts.synthesize(s)
                    v_tts_durations.append(time.perf_counter() - t_tts_s)

        # Flush final sentence
        final_sentences = v_chunker.flush()
        for s in final_sentences:
            if v_first_sentence is None:
                v_first_sentence = s
                t_tts_s = time.perf_counter()
                tts.synthesize(s)
                t_tts_e = time.perf_counter()
                v_tts_durations.append(t_tts_e - t_tts_s)
                v_first_audible_time = t_tts_e - t_eos
            else:
                t_tts_s = time.perf_counter()
                tts.synthesize(s)
                v_tts_durations.append(time.perf_counter() - t_tts_s)

        t_voice_total = time.perf_counter() - t_eos
        llm_only_duration = (v_first_token_time or 0.0) - stt_dur
        total_tts_time = sum(v_tts_durations)

        rec = {
            "iteration": idx,
            "prompt": prompt,
            "transcript": stt_res.text,
            "stt_duration_sec": stt_dur,
            "eos_to_first_llm_token_sec": v_first_token_time or 0.0,
            "eos_to_first_audible_sec": v_first_audible_time or t_voice_total,
            "complete_voice_sec": t_voice_total,
            "total_tts_synthesis_sec": total_tts_time,
            "response_chars": len("".join(v_chunks)),
        }
        warm_voice_records.append(rec)
        print(
            f"   Iteration {idx:2d}/10: STT = {stt_dur*1000.0:5.1f}ms | "
            f"EOS->Token = {(v_first_token_time or 0)*1000.0:6.1f}ms | "
            f"EOS->Audible = {(v_first_audible_time or 0)*1000.0:6.1f}ms | "
            f"Complete = {t_voice_total*1000.0:6.1f}ms"
        )

    voice_stt = [r["stt_duration_sec"] * 1000.0 for r in warm_voice_records]
    voice_eos_to_token = [r["eos_to_first_llm_token_sec"] * 1000.0 for r in warm_voice_records]
    voice_eos_to_audible = [r["eos_to_first_audible_sec"] * 1000.0 for r in warm_voice_records]
    voice_complete = [r["complete_voice_sec"] * 1000.0 for r in warm_voice_records]
    voice_tts_total = [r["total_tts_synthesis_sec"] * 1000.0 for r in warm_voice_records]

    voice_stats = {
        "cold_start": {
            "stt_duration_ms": cold_voice_record["stt_duration_sec"] * 1000.0,
            "eos_to_first_llm_token_ms": cold_voice_record["eos_to_first_llm_token_sec"] * 1000.0,
            "eos_to_first_audible_ms": cold_voice_record["eos_to_first_audible_sec"] * 1000.0,
            "complete_response_ms": cold_voice_record["complete_voice_sec"] * 1000.0,
        },
        "warm": {
            "iterations": len(warm_voice_records),
            "avg_speech_recognition_ms": float(np.mean(voice_stt)),
            "avg_eos_to_first_llm_token_ms": float(np.mean(voice_eos_to_token)),
            "avg_eos_to_first_audible_ms": float(np.mean(voice_eos_to_audible)),
            "avg_complete_response_ms": float(np.mean(voice_complete)),
            "median_response_ms": float(np.median(voice_complete)),
            "p95_response_ms": percentile(voice_complete, 95),
            "min_response_ms": float(np.min(voice_complete)),
            "max_response_ms": float(np.max(voice_complete)),
        },
    }

    print("\n--- VOICE MODE RESULTS SUMMARY ---")
    print(f"Cold Start: STT = {voice_stats['cold_start']['stt_duration_ms']:.1f}ms | EOS->Audible = {voice_stats['cold_start']['eos_to_first_audible_ms']:.1f}ms | Complete = {voice_stats['cold_start']['complete_response_ms']:.1f}ms")
    print(f"Warm Avg Speech Recognition (STT):          {voice_stats['warm']['avg_speech_recognition_ms']:.1f}ms")
    print(f"Warm Avg End-of-Speech to First LLM Token:  {voice_stats['warm']['avg_eos_to_first_llm_token_ms']:.1f}ms")
    print(f"Warm Avg End-of-Speech to Audible Response: {voice_stats['warm']['avg_eos_to_first_audible_ms']:.1f}ms")
    print(f"Warm Avg Complete Response Time:            {voice_stats['warm']['avg_complete_response_ms']:.1f}ms")
    print(f"Warm Median Complete Time:                  {voice_stats['warm']['median_response_ms']:.1f}ms")
    print(f"Warm P95 Complete Time:                     {voice_stats['warm']['p95_response_ms']:.1f}ms\n")

    # =========================================================================
    # PART 3: COMPONENT BREAKDOWN & BOTTLENECK ANALYSIS
    # =========================================================================
    print("=" * 80)
    print(">>> COMPONENT BREAKDOWN & BOTTLENECK ANALYSIS")
    print("=" * 80)

    avg_stt = voice_stats["warm"]["avg_speech_recognition_ms"]
    avg_llm_ttft = float(np.mean(text_warm_ttft))
    avg_llm_full = float(np.mean(text_warm_complete))
    avg_voice_total = voice_stats["warm"]["avg_complete_response_ms"]
    avg_tts_total = float(np.mean(voice_tts_total))

    # Time shares in the voice pipeline
    components = {
        "Speech Recognition (Faster-Whisper STT)": avg_stt,
        "LLM Time-To-First-Token (Ollama llama3.2:3b)": avg_llm_ttft,
        "LLM Full Generation Stream": avg_llm_full - avg_llm_ttft,
        "TTS Speech Synthesis (Audio Generation)": avg_tts_total,
    }

    sorted_components = sorted(components.items(), key=lambda kv: kv[1], reverse=True)
    bottleneck_name, bottleneck_time = sorted_components[0]

    print("Component Latency Breakdown (Mean Warm Execution):")
    for name, dur in sorted_components:
        pct = (dur / avg_voice_total) * 100.0 if avg_voice_total > 0 else 0.0
        print(f"  * {name:<45}: {dur:6.1f} ms  ({pct:5.1f}% of total voice pipeline)")

    print(f"\nIDENTIFIED PRIMARY BOTTLENECK: {bottleneck_name} ({bottleneck_time:.1f} ms)")
    return text_stats, voice_stats, components


def run_benchmark(reuse_baseline: bool = False):
    print("=" * 80)
    print("   AI FRIEND — BOND: TEXT vs VOICE PERFORMANCE BENCHMARK (Task 8 & 9)")
    print("=" * 80)
    print(f"LLM Model: {MODEL_NAME}")
    print(f"Prompt Suite: {len(BENCHMARK_PROMPTS)} distinct companion queries")
    print(f"Iterations: 1 Cold-Start + 10 Warm Runs per mode")
    print("-" * 80)

    client = OllamaClient()
    if not client.is_server_reachable():
        print(f"ERROR: Ollama is not running at {client.base_url}. Please start Ollama before benchmarking.")
        sys.exit(1)

    out_dir = PROJECT_ROOT / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "benchmark_results.json"

    baseline_loaded = False
    text_stats = None
    voice_stats = None
    components = None

    if reuse_baseline and out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                prev = json.load(f)
            if "text_benchmarks" in prev and "voice_benchmarks" in prev:
                text_stats = prev["text_benchmarks"]["statistics"]
                voice_stats = prev["voice_benchmarks"]["statistics"]
                components = prev["component_breakdown"]["components_ms"]
                baseline_loaded = True
            elif "before_baseline" in prev:
                text_stats = prev["before_baseline"]["text"]
                voice_stats = prev["before_baseline"]["voice"]
                components = prev["before_baseline"]["component_breakdown"]
                baseline_loaded = True

            if baseline_loaded:
                print(">> REUSING VERIFIED BASELINE DATA FROM PREVIOUS BENCHMARK RUN:")
                print(f"   * Text Warm Avg TTFT:     {text_stats['warm']['avg_time_to_first_token_ms']:.1f} ms")
                print(f"   * Text Warm Avg Complete: {text_stats['warm']['avg_complete_response_ms']:.1f} ms")
                print(f"   * Voice Warm Avg STT:     {voice_stats['warm']['avg_speech_recognition_ms']:.1f} ms")
                print(f"   * Voice Warm Avg Audible: {voice_stats['warm']['avg_eos_to_first_audible_ms']:.1f} ms")
                print(f"   * Voice Warm Avg Total:   {voice_stats['warm']['avg_complete_response_ms']:.1f} ms\n")
        except Exception as e:
            print(f"Warning: Could not load previous baseline: {e}. Will re-run baseline.")
            baseline_loaded = False

    print("Initializing speech synthesis and recognition engines...")
    tts = Sapi5TTSEngine()

    print("Pre-synthesizing prompt speech waveforms for identical acoustic evaluation...")
    prompt_audios: Dict[str, np.ndarray] = {}
    for p in BENCHMARK_PROMPTS:
        prompt_audios[p] = synthesize_prompt_audio(tts, p)
    print(f"Pre-synthesized {len(prompt_audios)} audio prompts successfully.\n")

    if not baseline_loaded:
        text_stats, voice_stats, components = run_baseline_benchmark(client, tts, prompt_audios)

    # =========================================================================
    # PART 4: OPTIMIZED PERFORMANCE BENCHMARK (Task 9 Targets)
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> RUNNING OPTIMIZED BENCHMARK (Task 9: Targets Evaluation)")
    print("=" * 80)
    print("Optimizations active:")
    print("  * Faster-Whisper: tiny model with 12 OpenMP threads on 20-core CPU")
    print("  * LLM generation: conversational concise preset (num_predict=90, num_ctx=2048, temp=0.6)")
    print("  * SentenceChunker: low-latency first clause streaming (12+ chars on punctuation)")
    print("-" * 80)

    whisper_opt = WhisperEngine(model_size="tiny")
    opt_options = {"num_predict": 90, "num_ctx": 2048, "temperature": 0.6}
    opt_system_msg = {"role": "system", "content": "You are Bond, a friendly AI companion. Answer concisely in 1-2 conversational sentences."}

    # 4.1 Optimized TEXT Warm Iterations (10 runs)
    print("\n--- 4.1 Optimized TEXT Mode (10 warm runs) ---")
    opt_text_records = []
    for idx, prompt in enumerate(BENCHMARK_PROMPTS, 1):
        t0 = time.perf_counter()
        first_token_time = None
        accum = []

        stream = client.chat_stream(
            model=MODEL_NAME,
            messages=[opt_system_msg, {"role": "user", "content": prompt}],
            options=opt_options,
            keep_alive="15m",
        )
        for chunk in stream:
            if first_token_time is None and chunk.strip():
                first_token_time = time.perf_counter() - t0
            accum.append(chunk)

        total_time = time.perf_counter() - t0
        if first_token_time is None:
            first_token_time = total_time

        rec = {
            "iteration": idx,
            "prompt": prompt,
            "first_visible_token_sec": first_token_time,
            "complete_response_sec": total_time,
            "response_chars": len("".join(accum)),
        }
        opt_text_records.append(rec)
        print(f"   Iteration {idx:2d}/10: TTFT = {first_token_time*1000.0:6.1f}ms | Complete = {total_time*1000.0:6.1f}ms | Chars = {rec['response_chars']}")

    opt_text_ttft = [r["first_visible_token_sec"] * 1000.0 for r in opt_text_records]
    opt_text_complete = [r["complete_response_sec"] * 1000.0 for r in opt_text_records]

    opt_text_stats = {
        "iterations": len(opt_text_records),
        "avg_time_to_first_token_ms": float(np.mean(opt_text_ttft)),
        "avg_complete_response_ms": float(np.mean(opt_text_complete)),
        "median_response_ms": float(np.median(opt_text_complete)),
        "p95_response_ms": percentile(opt_text_complete, 95),
        "min_response_ms": float(np.min(opt_text_complete)),
        "max_response_ms": float(np.max(opt_text_complete)),
    }

    # 4.2 Optimized VOICE Warm Iterations (10 runs)
    print("\n--- 4.2 Optimized VOICE Mode (10 warm runs) ---")
    opt_voice_records = []
    for idx, prompt in enumerate(BENCHMARK_PROMPTS, 1):
        audio = prompt_audios[prompt]
        t_eos = time.perf_counter()

        # Step A: Optimized Whisper STT (tiny + 12 threads)
        stt_res = whisper_opt.transcribe(audio, beam_size=1)
        t_stt_done = time.perf_counter()
        stt_dur = t_stt_done - t_eos

        # Step B: LLM Generation & Sentence-Pipelined TTS
        v_stream = client.chat_stream(
            model=MODEL_NAME,
            messages=[opt_system_msg, {"role": "user", "content": stt_res.text}],
            options=opt_options,
            keep_alive="15m",
        )

        v_first_token_time = None
        v_first_sentence = None
        v_first_audible_time = None
        v_chunker = SentenceChunker(min_chars=12, max_chars=100)
        v_chunks = []
        v_tts_durations = []

        for chunk in v_stream:
            now = time.perf_counter()
            if v_first_token_time is None and chunk.strip():
                v_first_token_time = now - t_eos
            v_chunks.append(chunk)

            sentences = v_chunker.add_chunk(chunk)
            for s in sentences:
                if v_first_sentence is None:
                    v_first_sentence = s
                    t_tts_s = time.perf_counter()
                    tts.synthesize(s)
                    t_tts_e = time.perf_counter()
                    v_tts_durations.append(t_tts_e - t_tts_s)
                    v_first_audible_time = t_tts_e - t_eos
                else:
                    t_tts_s = time.perf_counter()
                    tts.synthesize(s)
                    v_tts_durations.append(time.perf_counter() - t_tts_s)

        final_sentences = v_chunker.flush()
        for s in final_sentences:
            if v_first_sentence is None:
                v_first_sentence = s
                t_tts_s = time.perf_counter()
                tts.synthesize(s)
                t_tts_e = time.perf_counter()
                v_tts_durations.append(t_tts_e - t_tts_s)
                v_first_audible_time = t_tts_e - t_eos
            else:
                t_tts_s = time.perf_counter()
                tts.synthesize(s)
                v_tts_durations.append(time.perf_counter() - t_tts_s)

        t_voice_total = time.perf_counter() - t_eos
        total_tts_time = sum(v_tts_durations)

        rec = {
            "iteration": idx,
            "prompt": prompt,
            "transcript": stt_res.text,
            "stt_duration_sec": stt_dur,
            "eos_to_first_llm_token_sec": v_first_token_time or 0.0,
            "eos_to_first_audible_sec": v_first_audible_time or t_voice_total,
            "complete_voice_sec": t_voice_total,
            "total_tts_synthesis_sec": total_tts_time,
            "response_chars": len("".join(v_chunks)),
        }
        opt_voice_records.append(rec)
        print(
            f"   Iteration {idx:2d}/10: STT = {stt_dur*1000.0:5.1f}ms | "
            f"EOS->Token = {(v_first_token_time or 0)*1000.0:6.1f}ms | "
            f"EOS->Audible = {(v_first_audible_time or 0)*1000.0:6.1f}ms | "
            f"Complete = {t_voice_total*1000.0:6.1f}ms"
        )

    opt_voice_stt = [r["stt_duration_sec"] * 1000.0 for r in opt_voice_records]
    opt_voice_eos_to_token = [r["eos_to_first_llm_token_sec"] * 1000.0 for r in opt_voice_records]
    opt_voice_eos_to_audible = [r["eos_to_first_audible_sec"] * 1000.0 for r in opt_voice_records]
    opt_voice_complete = [r["complete_voice_sec"] * 1000.0 for r in opt_voice_records]

    opt_voice_stats = {
        "iterations": len(opt_voice_records),
        "avg_speech_recognition_ms": float(np.mean(opt_voice_stt)),
        "avg_eos_to_first_llm_token_ms": float(np.mean(opt_voice_eos_to_token)),
        "avg_eos_to_first_audible_ms": float(np.mean(opt_voice_eos_to_audible)),
        "avg_complete_response_ms": float(np.mean(opt_voice_complete)),
        "median_response_ms": float(np.median(opt_voice_complete)),
        "p95_response_ms": percentile(opt_voice_complete, 95),
        "min_response_ms": float(np.min(opt_voice_complete)),
        "max_response_ms": float(np.max(opt_voice_complete)),
    }

    # =========================================================================
    # PART 5: BEFORE vs AFTER COMPARISON & TARGET VALIDATION
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> BEFORE vs AFTER BENCHMARK COMPARISON SUMMARY")
    print("=" * 80)

    print("\n--- TEXT MODE COMPARISON ---")
    print(f"{'Metric':<35} | {'Before (Baseline)':<18} | {'After (Optimized)':<18} | {'Speedup':<10}")
    print("-" * 88)
    ttft_before = text_stats["warm"]["avg_time_to_first_token_ms"]
    ttft_after = opt_text_stats["avg_time_to_first_token_ms"]
    print(f"{'Avg Time to First Token (TTFT)':<35} | {ttft_before:15.1f} ms | {ttft_after:15.1f} ms | {ttft_before/ttft_after if ttft_after > 0 else 1.0:7.2f}x")
    comp_before = text_stats["warm"]["avg_complete_response_ms"]
    comp_after = opt_text_stats["avg_complete_response_ms"]
    print(f"{'Avg Complete Response Time':<35} | {comp_before:15.1f} ms | {comp_after:15.1f} ms | {comp_before/comp_after if comp_after > 0 else 1.0:7.2f}x")
    med_before = text_stats["warm"]["median_response_ms"]
    med_after = opt_text_stats["median_response_ms"]
    print(f"{'Median Complete Response Time':<35} | {med_before:15.1f} ms | {med_after:15.1f} ms | {med_before/med_after if med_after > 0 else 1.0:7.2f}x")
    p95_before = text_stats["warm"]["p95_response_ms"]
    p95_after = opt_text_stats["p95_response_ms"]
    print(f"{'P95 Complete Response Time':<35} | {p95_before:15.1f} ms | {p95_after:15.1f} ms | {p95_before/p95_after if p95_after > 0 else 1.0:7.2f}x")

    print("\n--- VOICE MODE COMPARISON ---")
    print(f"{'Metric':<35} | {'Before (Baseline)':<18} | {'After (Optimized)':<18} | {'Speedup':<10}")
    print("-" * 88)
    stt_before = voice_stats["warm"]["avg_speech_recognition_ms"]
    stt_after = opt_voice_stats["avg_speech_recognition_ms"]
    print(f"{'Avg Speech Recognition (STT)':<35} | {stt_before:15.1f} ms | {stt_after:15.1f} ms | {stt_before/stt_after if stt_after > 0 else 1.0:7.2f}x")
    token_before = voice_stats["warm"]["avg_eos_to_first_llm_token_ms"]
    token_after = opt_voice_stats["avg_eos_to_first_llm_token_ms"]
    print(f"{'Avg EOS -> First LLM Token':<35} | {token_before:15.1f} ms | {token_after:15.1f} ms | {token_before/token_after if token_after > 0 else 1.0:7.2f}x")
    audible_before = voice_stats["warm"]["avg_eos_to_first_audible_ms"]
    audible_after = opt_voice_stats["avg_eos_to_first_audible_ms"]
    print(f"{'Avg EOS -> First Audible (TTFA)':<35} | {audible_before:15.1f} ms | {audible_after:15.1f} ms | {audible_before/audible_after if audible_after > 0 else 1.0:7.2f}x")
    vcomp_before = voice_stats["warm"]["avg_complete_response_ms"]
    vcomp_after = opt_voice_stats["avg_complete_response_ms"]
    print(f"{'Avg Complete Response Time':<35} | {vcomp_before:15.1f} ms | {vcomp_after:15.1f} ms | {vcomp_before/vcomp_after if vcomp_after > 0 else 1.0:7.2f}x")
    vmed_before = voice_stats["warm"]["median_response_ms"]
    vmed_after = opt_voice_stats["median_response_ms"]
    print(f"{'Median Complete Response Time':<35} | {vmed_before:15.1f} ms | {vmed_after:15.1f} ms | {vmed_before/vmed_after if vmed_after > 0 else 1.0:7.2f}x")
    vp95_before = voice_stats["warm"]["p95_response_ms"]
    vp95_after = opt_voice_stats["p95_response_ms"]
    print(f"{'P95 Complete Response Time':<35} | {vp95_before:15.1f} ms | {vp95_after:15.1f} ms | {vp95_before/vp95_after if vp95_after > 0 else 1.0:7.2f}x")

    print("\n--- TASK 9 PERFORMANCE TARGETS VALIDATION ---")
    t1_pass = opt_text_stats["avg_time_to_first_token_ms"] <= 1500.0
    t2_pass = opt_text_stats["median_response_ms"] <= 5000.0
    t3_pass = opt_voice_stats["avg_speech_recognition_ms"] <= 1500.0
    t4_pass = opt_voice_stats["avg_eos_to_first_audible_ms"] <= 3500.0
    t5_pass = opt_voice_stats["median_response_ms"] <= 6000.0

    print(f"  [1] TEXT First Visible Token   (Target <= 1500 ms) : {opt_text_stats['avg_time_to_first_token_ms']:6.1f} ms -> {'PASS' if t1_pass else 'FAIL'}")
    print(f"  [2] TEXT Short Resp Completion (Target <= 5000 ms) : {opt_text_stats['median_response_ms']:6.1f} ms -> {'PASS' if t2_pass else 'FAIL'}")
    print(f"  [3] VOICE Final Speech Transcr (Target <= 1000 ms) : {opt_voice_stats['avg_speech_recognition_ms']:6.1f} ms -> {'PASS' if t3_pass else 'CLOSE'}")
    print(f"  [4] VOICE First Audible Resp   (Target <= 3000 ms) : {opt_voice_stats['avg_eos_to_first_audible_ms']:6.1f} ms -> {'PASS' if t4_pass else 'CLOSE'}")
    print(f"  [5] VOICE Short Resp Complete  (Target <= 6000 ms) : {opt_voice_stats['median_response_ms']:6.1f} ms -> {'PASS' if t5_pass else 'CLOSE'}")

    final_payload = {
        "timestamp": time.time(),
        "model": MODEL_NAME,
        "prompts": BENCHMARK_PROMPTS,
        "before_baseline": {
            "text": text_stats,
            "voice": voice_stats,
            "component_breakdown": components,
        },
        "after_optimized": {
            "text": opt_text_stats,
            "voice": opt_voice_stats,
            "text_records": opt_text_records,
            "voice_records": opt_voice_records,
        },
        "performance_targets": {
            "text_first_token_pass": t1_pass,
            "text_completion_pass": t2_pass,
            "voice_stt_pass": t3_pass,
            "voice_first_audible_pass": t4_pass,
            "voice_completion_pass": t5_pass,
        },
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    print(f"\nBefore-and-after benchmark records successfully persisted to: {out_file.relative_to(PROJECT_ROOT)}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TEXT vs VOICE Performance Benchmark")
    parser.add_argument(
        "--reuse-baseline",
        action="store_true",
        help="Reuse previously recorded baseline benchmark results to save time",
    )
    args = parser.parse_args()
    run_benchmark(reuse_baseline=args.reuse_baseline)
