"""Theme tokens and stylesheet builder for the WIMBA GUI.

Colours live here as two token sets (never hard-coded in the widgets), so a
theme switch is just re-applying a stylesheet built from a different set. Accents
are aligned to the WIMBA logo: deep logo blue as primary, teal/cyan as the
interactive accent.
"""
from __future__ import annotations

# WIMBA logo palette: deep blue #1f3a5f, teal/cyan, amber, green.
DARK = dict(
    bg="#151b23", panel="#1a212b", menubar="#10161d",
    line="#28323f", line2="#333f4e",
    ink="#d9e0e8", ink2="#9aa6b3", ink3="#6b7683",
    accent="#4cc2d6", primary="#3f6ea0", sel="#202a36", selbg="#1c3038",
)

# Light is "technical paper", not glaring white: soft grey-blue ground, graphite ink.
LIGHT = dict(
    bg="#f3f6f9", panel="#e8edf2", menubar="#e6ebf0",
    line="#d2d9e1", line2="#c0c9d3",
    ink="#22303f", ink2="#54606f", ink3="#8b95a2",
    accent="#1f7f8f", primary="#1f3a5f", sel="#dce3ea", selbg="#d3e6ec",
)

THEMES = {"dark": DARK, "light": LIGHT}


def build_style(t: dict) -> str:
    return f"""
QMainWindow, QWidget {{ background:{t['bg']}; color:{t['ink']};
  font-family:'Segoe UI',system-ui,sans-serif; font-size:13px; }}
QMainWindow::separator {{ background:{t['line']}; width:4px; height:4px; }}
QMainWindow::separator:hover {{ background:{t['accent']}; }}

QMenuBar {{ background:{t['menubar']}; border-bottom:1px solid {t['line']}; }}
QMenuBar::item {{ padding:5px 11px; color:{t['ink2']}; }}
QMenuBar::item:selected {{ background:{t['bg']}; color:{t['ink']}; }}
QMenu {{ background:{t['panel']}; border:1px solid {t['line2']}; padding:5px; }}
QMenu::item {{ padding:6px 24px 6px 12px; border-radius:4px; }}
QMenu::item:selected {{ background:{t['sel']}; }}
QMenu::separator {{ height:1px; background:{t['line']}; margin:5px 6px; }}

QDockWidget {{ color:{t['ink2']}; font-size:11px; }}
QDockWidget::title {{ background:{t['panel']}; padding:5px 9px;
  border-bottom:1px solid {t['line']}; }}

QTabWidget::pane {{ border:1px solid {t['line']}; top:-1px; }}
QTabBar::tab {{ background:{t['panel']}; color:{t['ink2']}; padding:6px 13px;
  border-right:1px solid {t['line']}; }}
QTabBar::tab:selected {{ background:{t['bg']}; color:{t['ink']};
  border-bottom:2px solid {t['accent']}; }}
QTabBar::tab:hover {{ color:{t['ink']}; }}

QStatusBar {{ background:{t['menubar']}; border-top:1px solid {t['line']};
  color:{t['ink2']}; font-family:'JetBrains Mono',monospace; font-size:11px; }}
QStatusBar::item {{ border:none; }}

QToolTip {{ background:{t['panel']}; color:{t['ink']}; border:1px solid {t['line2']}; }}

QLabel#Brand {{ color:{t['ink']}; font-weight:600; letter-spacing:.5px; padding-right:10px; }}
QLabel#EmptyIcon {{ color:{t['ink3']}; font-size:30px; }}
QLabel#EmptyTitle {{ color:{t['ink2']}; font-size:14px; font-weight:600; }}
QLabel#EmptyText  {{ color:{t['ink3']}; font-size:12px; }}
"""
