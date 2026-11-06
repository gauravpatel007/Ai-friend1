"""JARVIS Holographic Arc Reactor Character Rendering Engine.

Renders a cinematic, sci-fi JARVIS AI Core (Arc Reactor / Holographic Sphere)
inspired by Tony Stark's JARVIS interface in Iron Man:
- Multi-layered rotating orbital and HUD arc rings
- Breathing glow and radial energy bloom
- Kinetic state transitions:
    • IDLE: Floating reactor with subtle breathing pulse and rotating arc segments
    • LISTENING: Radar sweep rings, electric cyan aura, soundwave intake
    • THINKING: Fast orbital computation nodes, spinning lattice core
    • SPEAKING: Concentric expanding acoustic ripples + real-time lip/audio wave modulation
    • HAPPY: Golden-cyan radiant energy burst with particle flares
    • SLEEPING: Dim low-power standby mode with slow pulse
    • ERROR: Warning amber-red reactor overload with glitch alerts
    • DRAGGING: Kinetic warp compression with motion trails
- Real-time lip/audio amplitude synchronization (mouth_openness)
- Transparent background with high-DPI smooth antialiasing
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from app.character.states import CharacterState, get_animation_config
from app.desktop.jarvis_theme import COLORS, qcolor
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Project root for locating default assets
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CHARACTERS_DIR = _PROJECT_ROOT / "assets" / "characters"


class CharacterRenderer:
    """Renders the JARVIS Holographic Arc Reactor Core across all animation states."""

    # Predefined size presets tailored for holographic orb display
    SIZE_PRESETS = {
        "small": 120,
        "medium": 160,
        "large": 220,
    }

    def __init__(
        self,
        character_name: str = "jarvis",
        size: int = 160,
        characters_dir: Optional[Path] = None,
    ) -> None:
        self._character_name = character_name
        self._target_size = size
        self._characters_dir = characters_dir or _DEFAULT_CHARACTERS_DIR

        # Cache: state_name -> list of scaled QPixmaps (for animation frames)
        self._frame_cache: Dict[str, List[QPixmap]] = {}
        # Source pixmaps at master resolution (256x256)
        self._source_frames: Dict[str, List[QPixmap]] = {}

        self._current_state = "idle"
        self._current_frame_index = 0
        self._mouth_openness = 0.0

        self._load_character()

    @property
    def character_name(self) -> str:
        return self._character_name

    @property
    def target_size(self) -> int:
        return self._target_size

    @property
    def current_state(self) -> str:
        return self._current_state

    # ─── Loading & Caching ─────────────────────────────────────────────

    def _load_character(self) -> None:
        """Load character frames from sprite assets or fallback generators."""
        self._source_frames.clear()
        self._frame_cache.clear()

        # Check candidate directories
        candidate_dirs = [
            self._characters_dir / self._character_name,
            self._characters_dir / "robot",
            self._characters_dir / "buddy",
        ]
        active_char_dir = None
        for cdir in candidate_dirs:
            if cdir.exists() and (cdir / "idle.png").exists():
                active_char_dir = cdir
                break

        if active_char_dir is not None:
            logger.info("Loading 3D Buddy robot sprites from %s", active_char_dir)
            known_states = ["idle", "listening", "thinking", "speaking", "happy", "sleeping", "error", "dragging"]
            
            # Map of fallback states if some are not present
            state_map = {
                "error": "thinking",
                "dragging": "listening",
            }

            for state in known_states:
                fname = f"{state}.png"
                fpath = active_char_dir / fname
                if not fpath.exists() and state in state_map:
                    fpath = active_char_dir / f"{state_map[state]}.png"
                if not fpath.exists():
                    fpath = active_char_dir / "idle.png"

                if fpath.exists():
                    base_pix = QPixmap(str(fpath))
                    if not base_pix.isNull():
                        # Create gentle animated breathing frames (8 frames)
                        frames = self._generate_breathing_sequence(base_pix, frame_count=8, master_size=256)
                        self._source_frames[state] = frames

            # Ensure all CharacterState enum values exist
            for c_state in CharacterState:
                sname = c_state.name.lower()
                if sname not in self._source_frames:
                    if "idle" in self._source_frames:
                        self._source_frames[sname] = self._source_frames["idle"]
        else:
            # Fallback to programmatic Arc Reactor frames
            self._generate_all_fallback_states()

        self._rebuild_cache()
        logger.info(
            "Character '%s' initialized with states: %s at %dpx",
            self._character_name,
            list(self._source_frames.keys()),
            self._target_size,
        )

    def _generate_breathing_sequence(
        self, base_pixmap: QPixmap, frame_count: int = 8, master_size: int = 256
    ) -> List[QPixmap]:
        """Generate subtle vertical floating and breathing pulse for a static sprite."""
        scaled_base = base_pixmap.scaled(
            master_size, master_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        bw = scaled_base.width()
        bh = scaled_base.height()

        frames = []
        for i in range(frame_count):
            t = i / float(frame_count)
            # Gentle sinusoidal vertical float (-3px to +3px)
            y_float = math.sin(t * math.pi * 2.0) * 3.5

            canvas = QPixmap(master_size, master_size)
            canvas.fill(Qt.transparent)

            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

            x_pos = (master_size - bw) / 2.0
            y_pos = ((master_size - bh) / 2.0) + y_float
            painter.drawPixmap(int(x_pos), int(y_pos), scaled_base)
            painter.end()

            frames.append(canvas)
        return frames

    def _generate_all_fallback_states(self) -> None:
        """Generate programmatic frames for every character state at master size 256px."""
        for state in CharacterState:
            config = get_animation_config(state)
            sname = state.name.lower()
            self._source_frames[sname] = self._generate_state_frames(
                sname, max(6, config.frame_count), 256
            )

    def _rebuild_cache(self) -> None:
        """Scale master frames to target size with smooth antialiased sampling."""
        self._frame_cache.clear()
        for state, frames in self._source_frames.items():
            scaled_frames = []
            for pixmap in frames:
                scaled = pixmap.scaled(
                    QSize(self._target_size, self._target_size),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                scaled_frames.append(scaled)
            self._frame_cache[state] = scaled_frames

    def set_size(self, size: int) -> None:
        """Resize character and rebuild scaled frame cache."""
        new_size = max(60, min(size, 450))
        if new_size == self._target_size:
            return
        self._target_size = new_size
        self._rebuild_cache()

    def set_size_preset(self, preset: str) -> None:
        """Apply size preset ('small', 'medium', 'large')."""
        if preset in self.SIZE_PRESETS:
            self.set_size(self.SIZE_PRESETS[preset])

    def set_state(self, state: str) -> None:
        """Transition to another character animation state."""
        state_lower = state.lower().strip()
        if state_lower == "transcribing":
            state_lower = "thinking"
        elif state_lower in ("ready", "active"):
            state_lower = "idle"
        if state_lower == self._current_state:
            return
        if state_lower in self._frame_cache:
            self._current_state = state_lower
            self._current_frame_index = 0
        else:
            logger.debug("State '%s' unavailable, remaining in '%s'", state, self._current_state)

    def advance_frame(self) -> bool:
        """Advance animation to next frame. Returns True if frame changed."""
        frames = self._frame_cache.get(self._current_state, [])
        if len(frames) <= 1:
            return False
        self._current_frame_index = (self._current_frame_index + 1) % len(frames)
        return True

    @property
    def mouth_openness(self) -> float:
        return self._mouth_openness

    def set_mouth_openness(self, openness: float) -> None:
        """Set voice modulation ratio (0.0 to 1.0) for speech visualizer."""
        self._mouth_openness = max(0.0, min(1.0, float(openness)))

    def get_current_pixmap(self) -> QPixmap:
        """Return the active frame's scaled pixmap with real-time audio wave overlay."""
        frames = self._frame_cache.get(self._current_state, [])
        if not frames:
            return self._generate_fallback_pixmap(self._target_size)
        idx = self._current_frame_index % len(frames)
        base_pixmap = frames[idx]

        # Dynamic Audio Waveform Modulation during speech (guaranteed active indicator)
        if self._current_state == "speaking":
            pix = base_pixmap.copy()
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            w = float(pix.width())
            h = float(pix.height())
            cx = w / 2.0
            cy = h / 2.0

            # Dynamic speech energy ripples (baseline wave guaranteed even on low openness)
            wave_amp = max(0.20, self._mouth_openness)
            wave_r1 = (w * 0.38) + (wave_amp * 16.0)
            wave_r2 = (w * 0.44) + (wave_amp * 24.0)

            wave_c = QColor("#00FFFF")
            wave_c.setAlphaF(0.45 * wave_amp)
            p1 = QPen(wave_c)
            p1.setWidthF(max(1.5, 2.5 * wave_amp))
            painter.setPen(p1)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), wave_r1, wave_r1)

            wave_c.setAlphaF(0.25 * wave_amp)
            p2 = QPen(wave_c)
            p2.setWidthF(1.5)
            painter.setPen(p2)
            painter.drawEllipse(QPointF(cx, cy), wave_r2, wave_r2)

            # Central voice flare
            glow_flare = QRadialGradient(cx, cy, w * 0.22)
            glow_flare.setColorAt(0.0, QColor(255, 255, 255, int(180 * wave_amp)))
            glow_flare.setColorAt(0.5, QColor(0, 229, 255, int(110 * wave_amp)))
            glow_flare.setColorAt(1.0, QColor(0, 229, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow_flare))
            painter.drawEllipse(QPointF(cx, cy), w * 0.22, w * 0.22)

            painter.end()
            return pix

        return base_pixmap

    def get_render_size(self) -> QSize:
        """Return the size of current frame pixmap."""
        return self.get_current_pixmap().size()

    def switch_character(self, character_name: str) -> None:
        """Switch character profile and reload sprites."""
        if character_name == self._character_name:
            return
        self._character_name = character_name
        self._current_state = "idle"
        self._current_frame_index = 0
        self._load_character()

    def available_states(self) -> List[str]:
        return list(self._source_frames.keys())

    def available_characters(self) -> List[str]:
        chars = ["jarvis"]
        if self._characters_dir.exists():
            for d in self._characters_dir.iterdir():
                if d.is_dir() and d.name not in chars:
                    chars.append(d.name)
        return chars

    # ─── Programmatic ARC REACTOR Generation ───────────────────────────

    def _generate_state_frames(
        self, state: str, frame_count: int, size: int
    ) -> List[QPixmap]:
        """Generate smooth animation sequence for given state."""
        generators = {
            "idle": self._gen_idle_frames,
            "listening": self._gen_listening_frames,
            "thinking": self._gen_thinking_frames,
            "speaking": self._gen_speaking_frames,
            "happy": self._gen_happy_frames,
            "sleeping": self._gen_sleeping_frames,
            "error": self._gen_error_frames,
            "dragging": self._gen_dragging_frames,
        }
        gen = generators.get(state, self._gen_idle_frames)
        return gen(frame_count, size)

    def _create_canvas(self, size: int) -> tuple[QPixmap, QPainter]:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        return pixmap, painter

    # ─── State 1: IDLE (Floating Arc Reactor with Breathing Pulse) ──────

    def _gen_idle_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.44

        for i in range(count):
            t = i / float(count)  # 0.0 -> 1.0
            pixmap, p = self._create_canvas(size)

            # Gentle vertical float
            y_hover = math.sin(t * math.pi * 2.0) * (size * 0.02)
            c_center = QPointF(cx, cy + y_hover)

            # 1. Ambient Glow Halo
            pulse_mod = 0.85 + 0.25 * math.sin(t * math.pi * 2.0)
            self._draw_ambient_glow(p, c_center, r_outer * 1.05, QColor("#00BFFF"), pulse_mod)

            # 2. Outer Segmented Ring (Clockwise rotation)
            angle_outer = t * 360.0
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=8, gap_deg=10,
                color=QColor("#1A4A6C"), width=2.0, rotation=angle_outer
            )

            # 3. Outer Tick Marks
            self._draw_tick_ring(p, c_center, r_outer * 0.94, count=24, color=QColor("#00BFFF"), length=4.0)

            # 4. Middle Counter-Rotating Ring
            angle_mid = -t * 240.0
            self._draw_segmented_ring(
                p, c_center, r_outer * 0.76, segments=4, gap_deg=25,
                color=QColor("#00BFFF"), width=2.5, rotation=angle_mid
            )

            # 5. Inner Hex Core Lattice
            self._draw_hex_core_lattice(p, c_center, r_outer * 0.50, color=QColor("#103048"))

            # 6. Central Arc Reactor Core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.42,
                core_color=QColor("#00FFFF"), bright_color=QColor("#E0F7FF"),
                pulse=pulse_mod
            )

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 2: LISTENING (Sonar Radar Sweep & Electric Cyan Aura) ───

    def _gen_listening_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.45

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Bright active cyan glow
            pulse = 1.0 + 0.3 * math.sin(t * math.pi * 2.0)
            self._draw_ambient_glow(p, c_center, r_outer * 1.15, QColor("#00FFFF"), pulse)

            # Expanding Radar Pulse Waves
            for wave_idx in range(3):
                phase = (t + wave_idx / 3.0) % 1.0
                wave_r = (r_outer * 0.3) + phase * (r_outer * 0.75)
                alpha = (1.0 - phase) * 0.55
                w_col = QColor("#00FFFF")
                w_col.setAlphaF(alpha)
                pen = QPen(w_col)
                pen.setWidthF(1.8)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c_center, wave_r, wave_r)

            # Rapid Spinning Outer Ring
            angle_outer = t * 720.0
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=12, gap_deg=8,
                color=QColor("#00FFFF"), width=2.5, rotation=angle_outer
            )

            # Radar Sweep Beam
            sweep_angle = t * 360.0
            self._draw_radar_sweep(p, c_center, r_outer * 0.85, sweep_angle, QColor("#00FFFF"))

            # Central Core with Microphone / Audio Wave Symbol
            self._draw_reactor_core(
                p, c_center, r_outer * 0.44,
                core_color=QColor("#00FFFF"), bright_color=QColor("#FFFFFF"),
                pulse=pulse * 1.1
            )
            self._draw_center_glyph(p, c_center, size * 0.08, glyph="mic", color=QColor("#FFFFFF"))

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 3: THINKING (Computation Lattice & Orbital Nodes) ───────

    def _gen_thinking_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.44

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Dynamic cyan-purple computational glow
            pulse = 0.9 + 0.25 * math.sin(t * math.pi * 4.0)
            self._draw_ambient_glow(p, c_center, r_outer, QColor("#00D4FF"), pulse)

            # Segmented ring rotating fast
            angle_outer = -t * 540.0
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=6, gap_deg=18,
                color=QColor("#0080B0"), width=2.0, rotation=angle_outer
            )

            # Counter-rotating inner gear ring
            angle_inner = t * 720.0
            self._draw_tick_ring(p, c_center, r_outer * 0.82, count=36, color=QColor("#4DD9FF"), length=5.0)

            # 4 Orbital Nodes orbiting at different radii and speeds
            num_nodes = 4
            for n in range(num_nodes):
                orbit_r = r_outer * (0.55 + 0.25 * (n % 2))
                orbit_speed = 1.0 + (n * 0.5)
                node_angle = math.radians((t * 360.0 * orbit_speed) + (n * (360.0 / num_nodes)))
                nx = cx + orbit_r * math.cos(node_angle)
                ny = cy + orbit_r * math.sin(node_angle)

                # Node glow
                node_col = QColor("#00FFFF")
                node_col.setAlphaF(0.9)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(node_col))
                p.drawEllipse(QPointF(nx, ny), 4.5, 4.5)

                # Trailing arc line
                p.setPen(QPen(QColor(0, 255, 255, 60), 1.0, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c_center, orbit_r, orbit_r)

            # Rapid Spinning Core Lattice
            self._draw_reactor_core(
                p, c_center, r_outer * 0.38,
                core_color=QColor("#00E5FF"), bright_color=QColor("#FFFFFF"),
                pulse=pulse
            )
            self._draw_center_glyph(p, c_center, size * 0.07, glyph="tri", color=QColor("#FFFFFF"))

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 4: SPEAKING (Concentric Acoustic Ripples) ───────────────

    def _gen_speaking_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.44

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Voice modulation rhythm
            speech_energy = 0.85 + 0.35 * abs(math.sin(t * math.pi * 3.0))

            # Ambient Voice Bloom
            self._draw_ambient_glow(p, c_center, r_outer * 1.1, QColor("#00BFFF"), speech_energy)

            # Acoustic expanding ripples
            for ripple_i in range(3):
                r_phase = (t + (ripple_i / 3.0)) % 1.0
                rip_radius = (r_outer * 0.4) + r_phase * (r_outer * 0.6)
                rip_alpha = (1.0 - r_phase) * 0.7 * speech_energy
                rc = QColor("#4DD9FF")
                rc.setAlphaF(rip_radius / (r_outer * 1.2) * rip_alpha)
                pen = QPen(rc)
                pen.setWidthF(2.0)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c_center, rip_radius, rip_radius)

            # Outer Segmented Ring with audio needle ticks
            angle_outer = t * 180.0
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=10, gap_deg=10,
                color=QColor("#00BFFF"), width=2.2, rotation=angle_outer
            )

            # Radial Equalizer Needles
            num_bars = 20
            for b in range(num_bars):
                b_angle = math.radians((360.0 / num_bars) * b + angle_outer)
                bar_len = 3.0 + 7.0 * abs(math.sin((t * 6.0) + b)) * speech_energy
                x1 = cx + (r_outer * 0.78) * math.cos(b_angle)
                y1 = cy + (r_outer * 0.78) * math.sin(b_angle)
                x2 = cx + (r_outer * 0.78 + bar_len) * math.cos(b_angle)
                y2 = cy + (r_outer * 0.78 + bar_len) * math.sin(b_angle)
                p.setPen(QPen(QColor(0, 229, 255, 180), 1.5))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            # Core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.42,
                core_color=QColor("#00FFFF"), bright_color=QColor("#FFFFFF"),
                pulse=speech_energy
            )

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 5: HAPPY (Radiant Golden-Cyan Energy Burst) ─────────────

    def _gen_happy_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.45

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Energy burst curve (peaks in middle)
            burst = 1.0 + 0.45 * math.sin(t * math.pi)

            # Golden-Cyan brilliant flare
            self._draw_ambient_glow(p, c_center, r_outer * 1.25, QColor("#FFE066"), burst)
            self._draw_ambient_glow(p, c_center, r_outer * 0.9, QColor("#00FFFF"), burst)

            # Radiant Star Rays
            num_rays = 12
            ray_rot = t * 180.0
            for r_idx in range(num_rays):
                ang = math.radians((360.0 / num_rays) * r_idx + ray_rot)
                r_len = r_outer * (0.8 + 0.3 * burst)
                x2 = cx + r_len * math.cos(ang)
                y2 = cy + r_len * math.sin(ang)
                ray_col = QColor("#FFF275")
                ray_col.setAlphaF(0.4 * burst)
                p.setPen(QPen(ray_col, 2.0))
                p.drawLine(c_center, QPointF(x2, y2))

            # Outer rings expanded
            self._draw_segmented_ring(
                p, c_center, r_outer * burst, segments=6, gap_deg=14,
                color=QColor("#FFE066"), width=2.5, rotation=t * 360.0
            )

            # Ultra bright core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.46,
                core_color=QColor("#FFE57F"), bright_color=QColor("#FFFFFF"),
                pulse=burst * 1.2
            )

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 6: SLEEPING (Low-Power Dark Steel-Blue Standby) ──────────

    def _gen_sleeping_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.40

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Very slow, deep breathing pulse
            pulse = 0.5 + 0.2 * math.sin(t * math.pi * 2.0)

            # Dim standby halo
            self._draw_ambient_glow(p, c_center, r_outer * 0.9, QColor("#004060"), pulse)

            # Stationary dim outer ring
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=4, gap_deg=30,
                color=QColor("#102535"), width=1.5, rotation=45.0
            )

            # Dim inner core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.40,
                core_color=QColor("#005080"), bright_color=QColor("#4080A0"),
                pulse=pulse
            )

            # "STANDBY" text readout
            p.setPen(QPen(QColor(70, 130, 170, int(180 * pulse))))
            f = QFont("Share Tech Mono", int(size * 0.055))
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            p.setFont(f)
            p.drawText(
                QRectF(cx - size * 0.3, cy + r_outer * 0.45, size * 0.6, size * 0.15),
                Qt.AlignCenter,
                "STANDBY",
            )

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 7: ERROR (Amber-Red Overload Alert & Glitch) ─────────────

    def _gen_error_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.44

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)

            # Jitter / glitch vibration
            jitter_x = math.sin(t * 30.0) * 2.5
            c_center = QPointF(cx + jitter_x, cy)

            # Warning flare
            pulse = 1.0 + 0.4 * abs(math.sin(t * math.pi * 3.0))
            self._draw_ambient_glow(p, c_center, r_outer * 1.1, QColor("#FF3333"), pulse)

            # Broken warning rings
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=3, gap_deg=40,
                color=QColor("#FF4444"), width=3.0, rotation=t * 180.0
            )

            # Warning Hazard Core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.44,
                core_color=QColor("#FF2222"), bright_color=QColor("#FFAA00"),
                pulse=pulse
            )
            self._draw_center_glyph(p, c_center, size * 0.09, glyph="hazard", color=QColor("#FFFFFF"))

            p.end()
            frames.append(pixmap)
        return frames

    # ─── State 8: DRAGGING (Kinetic Warp & Trailing Energy Streaks) ─────

    def _gen_dragging_frames(self, count: int, size: int) -> List[QPixmap]:
        frames = []
        cx = size / 2.0
        cy = size / 2.0
        r_outer = size * 0.44

        for i in range(count):
            t = i / float(count)
            pixmap, p = self._create_canvas(size)
            c_center = QPointF(cx, cy)

            # Kinetic high energy glow
            self._draw_ambient_glow(p, c_center, r_outer * 1.2, QColor("#00E5FF"), 1.3)

            # Trailing motion streak lines (horizontal drift)
            for streak_i in range(5):
                sy = cy - (r_outer * 0.7) + (streak_i * r_outer * 0.35)
                trail_len = (size * 0.25) + 15.0 * math.sin((t * 5.0) + streak_i)
                streak_c = QColor("#00FFFF")
                streak_c.setAlphaF(0.4)
                p.setPen(QPen(streak_c, 1.5))
                p.drawLine(QPointF(cx - trail_len, sy), QPointF(cx + trail_len * 0.5, sy))

            # Compressed / warped outer rings
            angle_warp = t * 360.0
            self._draw_segmented_ring(
                p, c_center, r_outer, segments=8, gap_deg=12,
                color=QColor("#00FFFF"), width=2.8, rotation=angle_warp
            )

            # Bright active core
            self._draw_reactor_core(
                p, c_center, r_outer * 0.42,
                core_color=QColor("#00FFFF"), bright_color=QColor("#FFFFFF"),
                pulse=1.3
            )

            p.end()
            frames.append(pixmap)
        return frames

    # ─── Reusable Arc Reactor Painter Routines ─────────────────────────

    def _draw_ambient_glow(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        color: QColor,
        intensity: float = 1.0,
    ) -> None:
        """Draw multi-stop radial energy glow bloom behind the orb."""
        grad = QRadialGradient(center, radius)
        c_inner = QColor(color)
        c_inner.setAlphaF(min(1.0, 0.45 * intensity))
        c_mid = QColor(color)
        c_mid.setAlphaF(min(1.0, 0.15 * intensity))
        c_outer = QColor(color)
        c_outer.setAlphaF(0.0)

        grad.setColorAt(0.0, c_inner)
        grad.setColorAt(0.55, c_mid)
        grad.setColorAt(1.0, c_outer)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(center, radius, radius)

    def _draw_segmented_ring(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        segments: int,
        gap_deg: float,
        color: QColor,
        width: float,
        rotation: float = 0.0,
    ) -> None:
        """Draw circular ring broken into equal angular segments with gaps."""
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        span_per_seg = 360.0 / segments
        arc_span = span_per_seg - gap_deg
        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0)

        for i in range(segments):
            start_ang = rotation + (i * span_per_seg) + (gap_deg / 2.0)
            # QPainter.drawArc takes 1/16th degrees
            p.drawArc(rect, int(start_ang * 16), int(arc_span * 16))

    def _draw_tick_ring(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        count: int,
        color: QColor,
        length: float = 4.0,
    ) -> None:
        """Draw small perimeter tick marks along a circle."""
        pen = QPen(color)
        pen.setWidthF(1.2)
        p.setPen(pen)

        step = 360.0 / count
        cx = center.x()
        cy = center.y()

        for i in range(count):
            ang = math.radians(i * step)
            x1 = cx + (radius - length) * math.cos(ang)
            y1 = cy + (radius - length) * math.sin(ang)
            x2 = cx + radius * math.cos(ang)
            y2 = cy + radius * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_hex_core_lattice(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        color: QColor,
    ) -> None:
        """Draw a subtle hexagonal lattice inside the inner reactor chamber."""
        pen = QPen(color)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # Draw concentric hexagons
        for r_step in [radius * 0.45, radius * 0.8, radius]:
            path = QPainterPath()
            for i in range(6):
                ang = math.radians(60 * i)
                px = center.x() + r_step * math.cos(ang)
                py = center.y() + r_step * math.sin(ang)
                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            path.closeSubpath()
            p.drawPath(path)

    def _draw_reactor_core(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        core_color: QColor,
        bright_color: QColor,
        pulse: float = 1.0,
    ) -> None:
        """Draw the brilliant central Arc Reactor core sphere and inner flare."""
        curr_r = radius * (0.95 + 0.08 * pulse)

        # 1. Dark core backplate
        p.setPen(QPen(core_color, 1.5))
        p.setBrush(QBrush(QColor("#05101A")))
        p.drawEllipse(center, curr_r, curr_r)

        # 2. Concentric inner bloom
        grad = QRadialGradient(center, curr_r)
        c0 = QColor(bright_color)
        c0.setAlphaF(min(1.0, 0.95 * pulse))
        c1 = QColor(core_color)
        c1.setAlphaF(min(1.0, 0.65 * pulse))
        c2 = QColor(core_color)
        c2.setAlphaF(0.0)

        grad.setColorAt(0.0, c0)
        grad.setColorAt(0.45, c1)
        grad.setColorAt(1.0, c2)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(center, curr_r, curr_r)

        # 3. Brilliant center pinprick
        p.setBrush(QBrush(QColor(255, 255, 255, min(255, int(240 * pulse)))))
        p.drawEllipse(center, curr_r * 0.22, curr_r * 0.22)

    def _draw_radar_sweep(
        self,
        p: QPainter,
        center: QPointF,
        radius: float,
        angle: float,
        color: QColor,
    ) -> None:
        """Draw a rotating radar scanline beam."""
        c = QColor(color)
        c.setAlphaF(0.4)
        pen = QPen(c)
        pen.setWidthF(2.0)
        p.setPen(pen)

        rad = math.radians(angle)
        x2 = center.x() + radius * math.cos(rad)
        y2 = center.y() + radius * math.sin(rad)
        p.drawLine(center, QPointF(x2, y2))

    def _draw_center_glyph(
        self,
        p: QPainter,
        center: QPointF,
        size: float,
        glyph: str,
        color: QColor,
    ) -> None:
        """Draw a minimal HUD glyph in the center (mic, tri, hazard)."""
        pen = QPen(color)
        pen.setWidthF(1.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        cx = center.x()
        cy = center.y()

        if glyph == "mic":
            # Stylized capsule
            p.drawRoundedRect(QRectF(cx - size * 0.35, cy - size * 0.6, size * 0.7, size * 0.9), 3, 3)
            p.drawLine(QPointF(cx, cy + size * 0.3), QPointF(cx, cy + size * 0.7))
            p.drawLine(QPointF(cx - size * 0.4, cy + size * 0.7), QPointF(cx + size * 0.4, cy + size * 0.7))
        elif glyph == "tri":
            # Inverted reactor triangle
            path = QPainterPath()
            path.moveTo(cx, cy + size * 0.6)
            path.lineTo(cx - size * 0.6, cy - size * 0.45)
            path.lineTo(cx + size * 0.6, cy - size * 0.45)
            path.closeSubpath()
            p.drawPath(path)
        elif glyph == "hazard":
            # Warning triangle
            path = QPainterPath()
            path.moveTo(cx, cy - size * 0.65)
            path.lineTo(cx + size * 0.65, cy + size * 0.5)
            path.lineTo(cx - size * 0.65, cy + size * 0.5)
            path.closeSubpath()
            p.drawPath(path)
            p.drawPoint(QPointF(cx, cy + size * 0.25))
            p.drawLine(QPointF(cx, cy - size * 0.2), QPointF(cx, cy + size * 0.1))

    def _generate_fallback_pixmap(self, size: int) -> QPixmap:
        """Fallback safety pixmap if frames are empty."""
        pixmap, p = self._create_canvas(size)
        cx = size / 2.0
        cy = size / 2.0
        self._draw_reactor_core(
            p, QPointF(cx, cy), size * 0.4,
            core_color=QColor("#00BFFF"), bright_color=QColor("#FFFFFF")
        )
        p.end()
        return pixmap
