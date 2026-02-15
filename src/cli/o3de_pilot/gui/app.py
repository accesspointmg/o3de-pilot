# O3DE Pilot GUI - Application Entry Point
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Entry point for the O3DE Pilot GUI application.
"""

import sys
from typing import Optional
from pathlib import Path


def run_gui(manifest_path: Optional[Path] = None, demo: bool = False) -> int:
    """
    Run the O3DE Pilot GUI.
    
    Args:
        manifest_path: Optional path to a manifest file to load
        demo: If True, load demo objects for testing
        
    Returns:
        Exit code
    """
    # Import PySide6 here to allow CLI to work without it
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError:
        print("Error: PySide6 is required for the GUI.")
        print("Install it with: pip install PySide6")
        return 1
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("O3DE Pilot")
    app.setOrganizationName("O3DE")
    app.setApplicationVersion("0.1.0")
    
    # Apply O3DE-style dark theme
    app.setStyleSheet(_get_global_stylesheet())
    
    # Show splash screen immediately
    from .splash_screen import SplashScreen
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    
    # Create main window (hidden)
    splash.set_status("Initialising window...")
    from .main_window import MainWindow
    window = MainWindow()
    
    if manifest_path:
        splash.set_status("Loading manifest...")
        window.load_manifest(manifest_path)
    elif demo:
        splash.set_status("Loading demo objects...")
        window.load_demo_objects()
    else:
        # Load from resolver with splash progress updates
        window.load_from_resolver(status_callback=splash.set_status)
    
    # Transition: hide splash, show main window
    splash.finish()
    window.show()
    
    return app.exec()


def _get_global_stylesheet() -> str:
    """Get the global application stylesheet."""
    return """
        /* Global O3DE Dark Theme */
        
        QWidget {
            font-family: "Segoe UI", "Open Sans", sans-serif;
            font-size: 12px;
        }
        
        QToolTip {
            background-color: #2D2D2D;
            color: #EEEEEE;
            border: 1px solid #444444;
            padding: 4px;
        }
        
        QScrollBar:vertical {
            background-color: #2D2D2D;
            width: 10px;
            margin: 0;
        }
        
        QScrollBar::handle:vertical {
            background-color: #555555;
            min-height: 30px;
            border-radius: 5px;
            margin: 2px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #666666;
        }
        
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        QScrollBar:horizontal {
            background-color: #2D2D2D;
            height: 10px;
            margin: 0;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #555555;
            min-width: 30px;
            border-radius: 5px;
            margin: 2px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #666666;
        }
        
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """


def main():
    """CLI entry point for the GUI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="O3DE Pilot GUI")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to manifest file to load"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Load demo objects for testing"
    )
    
    args = parser.parse_args()
    
    sys.exit(run_gui(manifest_path=args.manifest, demo=args.demo))


if __name__ == "__main__":
    main()
