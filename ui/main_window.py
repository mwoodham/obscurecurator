from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QTabWidget, QSplitter, QGroupBox, QComboBox,
    QFileDialog, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QAction

import os
from pathlib import Path
import config
from ui.playback_control_ui import PlaybackControlUI
from media_processor.segment_selector import SegmentSelector

class MainWindow(QMainWindow):
    """Main application window with tabs for different functionality."""
    
    def __init__(self, processor, playback_engine, playback_controller, segment_selector):
        super().__init__()
        self.processor = processor
        self.playback_engine = playback_engine
        self.playback_controller = playback_controller
        self.segment_selector = segment_selector
        
        self.setWindowTitle("AI Media Collage")
        self.setMinimumSize(1000, 700)
        
        # Setup UI
        self._setup_menu()
        self._setup_ui()
        
        print("Main window initialized")
    
    def _setup_menu(self):
        """Setup application menu."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # Set media directory
        set_dir_action = QAction('Set Media Directory', self)
        set_dir_action.triggered.connect(self._set_media_directory)
        file_menu.addAction(set_dir_action)
        
        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Process menu
        process_menu = menubar.addMenu('Process')
        
        # Process all action
        process_all_action = QAction('Process All Media', self)
        process_all_action.triggered.connect(self._process_all_media)
        process_menu.addAction(process_all_action)
        
        # Playback menu
        playback_menu = menubar.addMenu('Playback')
        
        # Start playback action
        start_action = QAction('Start Playback', self)
        start_action.triggered.connect(self._start_playback)
        playback_menu.addAction(start_action)
        
        # Stop playback action
        stop_action = QAction('Stop Playback', self)
        stop_action.triggered.connect(self._stop_playback)
        playback_menu.addAction(stop_action)
    
    def _setup_ui(self):
        """Setup the main UI."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create layout
        layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # Add tabs
        self._create_process_tab(tab_widget)
        self._create_playback_tab(tab_widget)
        
        layout.addWidget(tab_widget)
        
        # Add status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")
    
    def _create_process_tab(self, tab_widget):
        """Create the process tab."""
        process_tab = QWidget()
        layout = QVBoxLayout(process_tab)
        
        # Media directory group
        dir_group = QGroupBox("Media Directory")
        dir_layout = QHBoxLayout(dir_group)
        
        self.dir_label = QLabel(str(config.MEDIA_DIR))
        dir_layout.addWidget(self.dir_label)
        
        change_dir_button = QPushButton("Change...")
        change_dir_button.clicked.connect(self._set_media_directory)
        dir_layout.addWidget(change_dir_button)
        
        layout.addWidget(dir_group)
        
        # Processing controls
        processing_group = QGroupBox("Processing Controls")
        processing_layout = QVBoxLayout(processing_group)
        
        # Processing buttons
        process_button = QPushButton("Process All Media Files")
        process_button.clicked.connect(self._process_all_media)
        processing_layout.addWidget(process_button)
        
        # Progress bar
        self.process_progress = QProgressBar()
        self.process_progress.setRange(0, 100)
        self.process_progress.setValue(0)
        processing_layout.addWidget(self.process_progress)
        
        # Status
        self.process_status = QLabel("Ready to process media")
        processing_layout.addWidget(self.process_status)
        
        layout.addWidget(processing_group)
        
        # Processing options
        options_group = QGroupBox("Processing Options")
        options_layout = QVBoxLayout(options_group)
        
        # Segment extraction options
        extract_layout = QHBoxLayout()
        extract_layout.addWidget(QLabel("Extraction Method:"))
        
        self.extract_method = QComboBox()
        self.extract_method.addItems(["Scene Detection", "Fixed Duration", "Both"])
        extract_layout.addWidget(self.extract_method)
        
        options_layout.addLayout(extract_layout)
        
        # Feature extraction options
        feature_layout = QHBoxLayout()
        feature_layout.addWidget(QLabel("Feature Extraction:"))
        
        self.feature_method = QComboBox()
        self.feature_method.addItems(["CLIP", "Color Histogram", "Both"])
        feature_layout.addWidget(self.feature_method)
        
        options_layout.addLayout(feature_layout)
        
        layout.addWidget(options_group)
        
        # Add spacer
        layout.addStretch()
        
        tab_widget.addTab(process_tab, "Process Media")
    
    def _create_playback_tab(self, tab_widget):
        """Create the playback tab."""
        # Reuse the PlaybackControlUI for this tab
        playback_ui = PlaybackControlUI(self.playback_controller, self.segment_selector)
        
        tab_widget.addTab(playback_ui, "Playback")
    
    def _set_media_directory(self):
        """Set the media directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Media Directory", str(config.MEDIA_DIR)
        )
        
        if directory:
            config.MEDIA_DIR = Path(directory)
            self.dir_label.setText(str(config.MEDIA_DIR))
            
            # Update status
            self.status_bar.showMessage(f"Media directory set to: {directory}")
    
    def _process_all_media(self):
        """Process all media files."""
        # Update UI
        self.process_status.setText("Processing media files...")
        self.process_progress.setValue(10)
        
        # Process in background
        # In a real implementation, you would use a worker thread
        # and update progress periodically
        self.processor.process_all()
        
        # Update UI
        self.process_progress.setValue(100)
        self.process_status.setText("Processing complete")
        self.status_bar.showMessage("Media processing complete")
    
    def _start_playback(self):
        """Start playback."""
        self.playback_controller.start()
        self.status_bar.showMessage("Playback started")
    
    def _stop_playback(self):
        """Stop playback."""
        self.playback_controller.stop()
        self.status_bar.showMessage("Playback stopped")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop playback
        self.playback_controller.stop()
        
        # Accept the close event
        event.accept()