from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QGroupBox, QScrollArea, QGridLayout,
    QSlider, QCheckBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QFont

from database.schema import VideoSegment, Tag
from media_processor.segment_selector import SegmentSelector
from playback.playback_controller import PlaybackController

class PlaybackControlUI(QMainWindow):
    """User interface for controlling AI-driven media collage playback."""
    
    def __init__(self, playback_controller, segment_selector):
        super().__init__()
        
        self.playback_controller = playback_controller
        self.segment_selector = segment_selector
        
        self.setWindowTitle("AI Media Collage")
        self.setMinimumSize(800, 600)
        
        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create main layout
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Setup UI components
        self._setup_header()
        self._setup_playback_controls()
        self._setup_concept_browser()
        self._setup_segment_list()
        
        # Timer for updating UI
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start(500)  # Update every 500ms
        
        print("Playback UI initialized")
    
    def _setup_header(self):
        """Setup header with title and description."""
        header_box = QGroupBox("AI Media Collage")
        header_layout = QVBoxLayout(header_box)
        
        # Title
        title_label = QLabel("AI-Driven Media Collage")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Create dynamic collages from video segments using AI-driven semantic analysis"
        )
        desc_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(desc_label)
        
        self.main_layout.addWidget(header_box)
    
    def _setup_playback_controls(self):
        """Setup controls for playback."""
        control_box = QGroupBox("Playback Controls")
        control_layout = QVBoxLayout(control_box)
        
        # Mode selector
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Playback Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Similar Content",
            "Contrasting Content",
            "Concept Chain",
            "Random",
            "Diverse Mix"
        ])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.currentIndexChanged.connect(self._change_mode)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        control_layout.addLayout(mode_layout)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Play button
        self.play_button = QPushButton("Start Playback")
        self.play_button.clicked.connect(self._toggle_playback)
        button_layout.addWidget(self.play_button)
        
        # Skip button
        skip_button = QPushButton("Skip Segment")
        skip_button.clicked.connect(self._skip_segment)
        button_layout.addWidget(skip_button)
        
        # Regenerate button
        regenerate_button = QPushButton("Regenerate Sequence")
        regenerate_button.clicked.connect(self._regenerate_sequence)
        button_layout.addWidget(regenerate_button)
        
        control_layout.addLayout(button_layout)
        
        # Options layout
        options_layout = QHBoxLayout()
        
        # Display window checkbox
        self.display_checkbox = QCheckBox("Show Display Window")
        self.display_checkbox.setChecked(True)
        self.display_checkbox.stateChanged.connect(self._toggle_display)
        options_layout.addWidget(self.display_checkbox)
        
        control_layout.addLayout(options_layout)
        
        self.main_layout.addWidget(control_box)
    
    def _setup_concept_browser(self):
        """Setup concept browser for selecting content by concept."""
        concept_box = QGroupBox("Concept Browser")
        concept_layout = QVBoxLayout(concept_box)
        
        # Create grid for concept buttons
        concept_grid = QGridLayout()
        
        # We'll populate this with the most common concepts
        self.concept_buttons = []
        
        # Load common concepts
        common_concepts = self.segment_selector.get_common_tags(count=20)
        
        # Create buttons for each concept
        for i, (concept, count) in enumerate(common_concepts):
            button = QPushButton(f"{concept} ({count})")
            button.setProperty("concept", concept)
            button.clicked.connect(self._concept_clicked)
            
            row, col = divmod(i, 4)  # 4 columns
            concept_grid.addWidget(button, row, col)
            self.concept_buttons.append(button)
        
        concept_layout.addLayout(concept_grid)
        
        self.main_layout.addWidget(concept_box)
    
    def _setup_segment_list(self):
        """Setup list to show current sequence of segments."""
        list_box = QGroupBox("Current Sequence")
        list_layout = QVBoxLayout(list_box)
        
        # Create list widget
        self.segment_list = QListWidget()
        list_layout.addWidget(self.segment_list)
        
        self.main_layout.addWidget(list_box)
    
    def _update_ui(self):
        """Update UI with current playback information."""
        # Update segment list
        self._update_segment_list()
    
    def _update_segment_list(self):
        """Update the segment list with current sequence."""
        current_sequence = self.playback_controller.current_sequence
        current_position = self.playback_controller.sequence_position
        
        # Clear list
        self.segment_list.clear()
        
        # Add items
        for i, segment in enumerate(current_sequence):
            # Get source file info
            source_file = segment.source_file
            
            # Create item text
            item_text = f"{source_file.filename} [{segment.start_frame}-{segment.end_frame}]"
            
            # Get tags for the segment
            session = self.segment_selector.db_manager.get_session()
            try:
                tags = session.query(Tag)\
                    .filter_by(segment_id=segment.id, tag_type='dominant_concept')\
                    .order_by(Tag.confidence.desc())\
                    .limit(3)\
                    .all()
                
                if tags:
                    tag_text = ", ".join([tag.tag_value for tag in tags])
                    item_text += f" - Tags: {tag_text}"
            finally:
                session.close()
            
            # Create list item
            item = QListWidgetItem(item_text)
            
            # Highlight current segment
            if i == current_position - 1:  # Current segment (already played)
                item.setBackground(Qt.yellow)
            elif i < current_position - 1:  # Past segments
                item.setBackground(Qt.lightGray)
                
            self.segment_list.addItem(item)
    
    def _toggle_playback(self):
        """Toggle playback state."""
        if self.playback_controller.keep_running:
            # Stop playback
            self.playback_controller.stop()
            self.play_button.setText("Start Playback")
        else:
            # Start playback
            mode_index = self.mode_combo.currentIndex()
            playback_mode = self._index_to_mode(mode_index)
            
            self.playback_controller.start(initial_mode=playback_mode)
            self.play_button.setText("Stop Playback")
            
            # Show display window if checked
            if self.display_checkbox.isChecked():
                self.playback_controller.show_playback_window()
    
    def _skip_segment(self):
        """Skip to the next segment."""
        self.playback_controller.skip_segment()
    
    def _regenerate_sequence(self):
        """Regenerate the sequence."""
        # Queue regenerate event
        self.playback_controller.playback_events.put(('regenerate', None))
    
    def _change_mode(self, index):
        """Change the playback mode."""
        mode = self._index_to_mode(index)
        if self.playback_controller.keep_running:
            self.playback_controller.set_mode(mode)
    
    def _index_to_mode(self, index):
        """Convert combo box index to mode string."""
        mode_map = {
            0: 'similar',
            1: 'contrast',
            2: 'concept_chain',
            3: 'random',
            4: 'diverse'
        }
        return mode_map.get(index, 'similar')
    
    def _toggle_display(self, state):
        """Toggle display window visibility."""
        if state == Qt.Checked:
            self.playback_controller.show_playback_window()
        else:
            self.playback_controller.playback_engine.display_window.hide()
    
    def _concept_clicked(self):
        """Handle concept button click."""
        # Get the concept from the button
        button = self.sender()
        concept = button.property("concept")
        
        # Find segments with this concept
        segments = self.segment_selector.find_segments_by_concept(concept, limit=10)
        
        if segments:
            # Update the sequence with these segments
            with self.playback_controller.sequence_lock:
                self.playback_controller.current_sequence = segments
                self.playback_controller.sequence_position = 0
                self.playback_controller._queue_next_segment()
                
            print(f"Created new sequence with concept: {concept}")
        else:
            print(f"No segments found for concept: {concept}")